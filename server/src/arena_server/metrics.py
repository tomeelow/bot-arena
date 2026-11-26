"""Phase 10 metrics, from our own database only: no trackers, no third-party analytics.

`usage` feeds the public /stats page and `health` the admin page and the alerts that
`ops guard` sends. Every figure is one query (convergence also replays the ratings fold), and
server/tests/test_metrics.py checks each against a fixture database.

"Players" are GitHub accounts: the built-in arena account has no GitHub id and never counts.
"""

import math
import shutil
import sqlite3
from datetime import datetime

from arena.runner import Failure

from .ratings import RATED_KINDS, Ratings, fold
from .schemas import DayCount, HealthReport, Spread, UsageStats
from .settings import Settings
from .store import EGRESS_CAPPED, PAUSED, Store

PLAYER_VERSIONS = """
    SELECT v.id, v.created_at FROM bot_versions v
    JOIN bots b ON b.id = v.bot_id JOIN users u ON u.id = b.owner_id
    WHERE u.github_id IS NOT NULL AND v.status IN ('active', 'retired')"""
BOT_FAULTS = [*(f.value for f in Failure), "both_failed"]


def seconds(later: str, earlier: str) -> str:
    """SQL for the seconds between two of our UTC timestamps."""
    return f"(julianday({later}) - julianday({earlier})) * 86400"


def spread(values: list[float]) -> Spread:
    """Nearest-rank median and 95th percentile."""
    ordered = sorted(values)

    def rank(q: float) -> float | None:
        return ordered[math.ceil(q * len(ordered)) - 1] if ordered else None

    return Spread(n=len(ordered), p50=rank(0.5), p95=rank(0.95))


def usage(conn: sqlite3.Connection, ratings: Ratings, settings: Settings) -> UsageStats:
    since = f"-{settings.stats_days} days"
    games, hours, unconverged = converge(conn, ratings, settings)
    rated = conn.execute(
        f"""SELECT r.end_reason, count(*) FROM results r JOIN matches m ON m.id = r.match_id
            WHERE m.kind IN {RATED_KINDS!r} AND r.finished_at >= datetime('now', ?)
            GROUP BY r.end_reason""",
        (since,),
    ).fetchall()
    total = sum(n for _, n in rated)
    by_reason = dict(rated)
    return UsageStats(
        submitted_bots=conn.execute(
            f"SELECT count(DISTINCT bot_id) FROM bot_versions WHERE id IN "
            f"(SELECT id FROM ({PLAYER_VERSIONS}))"
        ).fetchone()[0],
        active_players_7d=conn.execute(
            """SELECT count(*) FROM (
                 SELECT b.owner_id FROM bot_versions v JOIN bots b ON b.id = v.bot_id
                 JOIN users u ON u.id = b.owner_id
                 WHERE u.github_id IS NOT NULL AND v.created_at >= datetime('now', '-7 days')
                 UNION
                 SELECT requester_id FROM comparisons
                 WHERE created_at >= datetime('now', '-7 days'))"""
        ).fetchone()[0],
        versions_per_day=days(
            conn,
            f"""SELECT date(created_at), count(*) FROM ({PLAYER_VERSIONS})
                WHERE created_at >= date('now', ?) GROUP BY 1 ORDER BY 1""",
            since,
        ),
        matches_per_day=days(
            conn,
            f"""SELECT date(finished_at), count(*) FROM results WHERE match_id IN
                  (SELECT id FROM matches WHERE kind IN {RATED_KINDS!r})
                AND finished_at >= date('now', ?) GROUP BY 1 ORDER BY 1""",
            since,
        ),
        converged_versions=len(games),
        unconverged_versions=unconverged,
        games_to_converge=spread(games),
        hours_to_converge=spread(hours),
        seconds_to_first_match=spread(
            [
                r[0]
                for r in conn.execute(
                    f"""SELECT {seconds("min(r.finished_at)", "v.created_at")}
                        FROM ({PLAYER_VERSIONS}) v
                        JOIN match_players mp ON mp.bot_version_id = v.id
                        JOIN matches m ON m.id = mp.match_id AND m.kind IN {RATED_KINDS!r}
                        JOIN results r ON r.match_id = m.id
                        GROUP BY v.id"""
                )
            ]
        ),
        rated_matches=total,
        sandbox_outcomes={f: by_reason.get(f, 0) / total if total else 0.0 for f in BOT_FAULTS},
    )


def converge(
    conn: sqlite3.Connection, ratings: Ratings, settings: Settings
) -> tuple[list[float], list[float], int]:
    """For each player version whose sigma fell below the provisional threshold: the rated
    games it took, and the hours from upload to that game. Also how many haven't yet."""
    created = {v: datetime.fromisoformat(at) for v, at in conn.execute(PLAYER_VERSIONS).fetchall()}
    finished = dict(conn.execute("SELECT match_id, finished_at FROM results").fetchall())
    games: list[float] = []
    hours: list[float] = []
    done: set[int] = set()
    for row, *after in fold(conn, ratings):
        for version, rating in zip((row["v0"], row["v1"]), after, strict=True):
            if version not in created or version in done:
                continue
            if rating.sigma < settings.provisional_sigma:
                done.add(version)
                games.append(rating.games)
                at = datetime.fromisoformat(finished[row["match_id"]])
                hours.append((at - created[version]).total_seconds() / 3600)
    return games, hours, len(created) - len(done)


def days(conn: sqlite3.Connection, query: str, since: str) -> list[DayCount]:
    return [DayCount(day=d, count=n) for d, n in conn.execute(query, (since,))]


def health(conn: sqlite3.Connection, store: Store, settings: Settings) -> HealthReport:
    window = (f"-{settings.health_window_h} hours",)

    def count(where: str) -> int:
        return conn.execute(
            f"SELECT count(*) FROM matches WHERE finished_at >= datetime('now', ?) AND {where}",
            window,
        ).fetchone()[0]

    finished = count("status = 'done'")
    errors = count("status = 'void' AND void_reason LIKE 'platform_error%'")
    expired = count("status = 'void' AND void_reason = 'lease expired'")
    durations = conn.execute(
        f"""SELECT {seconds("finished_at", "started_at")}, worker_id FROM matches
            WHERE status = 'done' AND started_at IS NOT NULL
            AND finished_at >= datetime('now', ?)""",
        window,
    ).fetchall()
    workers = len({w for _, w in durations})
    oldest = conn.execute(
        f"SELECT max({seconds("datetime('now')", 'created_at')}) FROM matches "
        "WHERE status = 'queued'"
    ).fetchone()[0]
    waits = [
        r[0]
        for r in conn.execute(
            f"""SELECT {seconds("started_at", "created_at")} FROM matches
                WHERE started_at >= datetime('now', ?)""",
            window,
        )
    ]
    disk = shutil.disk_usage(store.root)
    report = HealthReport(
        window_h=settings.health_window_h,
        alerts=[],
        matches_finished=finished,
        platform_errors=errors,
        lease_expired=expired,
        platform_error_rate=errors / (finished + errors + expired) if errors else 0.0,
        end_reasons=dict(
            conn.execute(
                """SELECT r.end_reason, count(*) FROM results r JOIN matches m ON m.id = r.match_id
                   WHERE m.finished_at >= datetime('now', ?) GROUP BY 1 ORDER BY 1""",
                window,
            ).fetchall()
        ),
        match_seconds=spread([d for d, _ in durations]),
        queue_depth=conn.execute("SELECT count(*) FROM matches WHERE status = 'queued'").fetchone()[
            0
        ],
        oldest_queued_s=oldest,
        queue_wait_s=spread(waits),
        worker_utilisation=(
            sum(d for d, _ in durations) / (settings.health_window_h * 3600 * workers)
            if workers
            else None
        ),
        disk_used_fraction=disk.used / disk.total,
    )
    report.alerts = alerts(report, store, settings)
    return report


def alerts(report: HealthReport, store: Store, settings: Settings) -> list[str]:
    """What an admin must hear about. `ops guard` reports these to the uptime checker."""
    found = []
    if report.platform_errors:
        found.append(f"{report.platform_errors} platform errors in {report.window_h} h")
    if report.disk_used_fraction >= settings.alert_disk_fraction:
        found.append(f"disk {report.disk_used_fraction:.0%} full")
    waited = max(report.oldest_queued_s or 0, report.queue_wait_s.p95 or 0)
    if waited > settings.alert_queue_wait_s:
        found.append(f"a match waited {waited / 60:.0f} min to start")
    if store.paused:
        found.append(f"ladder paused: {(store.root / PAUSED).read_text().strip()}")
    if (store.root / EGRESS_CAPPED).exists():
        found.append("site off: this month's egress budget is spent")
    return found
