"""Every Phase 10 metric, checked against a small database whose answers are known."""

import shutil
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from arena_server import bots, metrics, ops
from arena_server.ratings import Ratings
from arena_server.settings import Settings
from arena_server.store import Store

SETTINGS = Settings.load()
RATINGS = Ratings(SETTINGS)


class Fixture:
    """Rows with chosen timestamps, given as hours ago."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.github_ids = iter(range(100, 1000))

    def player(self, handle: str) -> int:
        return bots.login_user(self.conn, next(self.github_ids), handle)

    def version(self, owner: int, bot: str, hours_ago: float, status: str = "active") -> int:
        found = self.conn.execute(
            "SELECT id FROM bots WHERE owner_id = ? AND name = ?", (owner, bot)
        ).fetchone()
        bot_id = found[0] if found else bots.create_bot(self.conn, owner, bot)
        n = self.conn.execute(
            "SELECT count(*) + 1 FROM bot_versions WHERE bot_id = ?", (bot_id,)
        ).fetchone()[0]
        return self.conn.execute(
            """INSERT INTO bot_versions (bot_id, n, code, status, created_at)
               VALUES (?, ?, ?, ?, datetime('now', ?)) RETURNING id""",
            (bot_id, n, f"sha256:{bot_id}{n}", status, ago(hours_ago)),
        ).fetchone()[0]

    def match(
        self,
        players: tuple[int, int],
        *,
        kind: str = "ranked",
        status: str = "done",
        created: float = 3,
        started: float | None = 2,
        finished: float | None = 1,
        reason: str = "core_destroyed",
        void_reason: str | None = None,
        worker: str = "w1",
    ) -> int:
        match = self.conn.execute(
            """INSERT INTO matches (kind, status, seed, engine_version, worker_id, void_reason,
                                    created_at, started_at, finished_at)
               VALUES (?, ?, 1, '1.0.0', ?, ?, datetime('now', ?),
                       datetime('now', ?), datetime('now', ?)) RETURNING id""",
            (kind, status, worker, void_reason, ago(created), ago(started), ago(finished)),
        ).fetchone()[0]
        for seat, version in enumerate(players):
            self.conn.execute("INSERT INTO match_players VALUES (?, ?, ?)", (match, seat, version))
        if status == "done":
            self.conn.execute(
                """INSERT INTO results (match_id, winner_seat, end_reason, turns, replay_sha256,
                                        finished_at, seq)
                   VALUES (?, 0, ?, 100, 'sha256:x', datetime('now', ?),
                           (SELECT coalesce(max(seq), 0) + 1 FROM results))""",
                (match, reason, ago(finished)),
            )
        return match

    def compare(self, requester: int, a: int, b: int, hours_ago: float) -> None:
        self.conn.execute(
            """INSERT INTO comparisons (requester_id, challenger_id, incumbent_id, created_at)
               VALUES (?, ?, ?, datetime('now', ?))""",
            (requester, a, b, ago(hours_ago)),
        )


def ago(hours: float | None) -> str | None:
    return None if hours is None else f"-{hours} hours"


@pytest.fixture
def f(db) -> Fixture:
    return Fixture(db)


def test_submitted_bots_count_player_bots_with_a_validated_version(f, db):
    ada, bob = f.player("ada"), f.player("bob")
    f.version(ada, "one", 5, "retired")
    f.version(ada, "one", 4)
    f.version(ada, "broken", 3, "rejected")
    f.version(bob, "two", 2)
    bots.builtin_version(db, "random")  # the arena's own bots never count
    assert metrics.usage(db, RATINGS, SETTINGS).submitted_bots == 2


def test_active_players_uploaded_or_compared_in_the_last_7_days(f, db):
    ada, bob, cy = f.player("ada"), f.player("bob"), f.player("cy")
    f.version(ada, "a", 48)
    old = f.version(bob, "b", 240)
    f.version(cy, "c", 240)
    f.compare(bob, old, old, 24)
    assert metrics.usage(db, RATINGS, SETTINGS).active_players_7d == 2


def test_versions_and_matches_per_day(f, db):
    ada, bob = f.player("ada"), f.player("bob")
    a1 = f.version(ada, "a", 50)
    f.version(ada, "a", 49, "retired")
    b1 = f.version(bob, "b", 1)
    f.version(bob, "rejected", 1, "rejected")
    f.match((a1, b1), finished=1)
    f.match((a1, b1), kind="placement", finished=1)
    f.match((a1, b1), kind="comparison", finished=1)  # unrated
    f.match((a1, b1), status="void", finished=1, void_reason="platform_error: x")
    day = {h: db.execute("SELECT date('now', ?)", (ago(h),)).fetchone()[0] for h in (1, 49, 50)}
    stats = metrics.usage(db, RATINGS, SETTINGS)
    per_day: dict[str, int] = {}
    for h in (50, 49, 1):
        per_day[day[h]] = per_day.get(day[h], 0) + 1
    assert {d.day: d.count for d in stats.versions_per_day} == per_day
    assert [(d.day, d.count) for d in stats.matches_per_day] == [(day[1], 2)]


def test_convergence_counts_games_and_hours_until_sigma_is_below_the_threshold(f, db):
    ada, bob = f.player("ada"), f.player("bob")
    a = f.version(ada, "a", 5)
    b = f.version(bob, "b", 4)
    f.version(bob, "idle", 4)  # never played: not converged
    anchor = bots.builtin_version(db, "random")
    f.match((a, anchor), finished=2)
    f.match((b, a), finished=1)
    # One game is enough, so the numbers are easy to read off.
    one_game = replace(SETTINGS, provisional_sigma=RATINGS.prior().sigma - 1e-9)
    stats = metrics.usage(db, RATINGS, one_game)
    assert (stats.converged_versions, stats.unconverged_versions) == (2, 1)
    assert (stats.games_to_converge.p50, stats.games_to_converge.p95) == (1, 1)
    assert sorted(metrics.converge(db, RATINGS, one_game)[1]) == pytest.approx([3, 3], abs=0.01)


def test_time_to_first_match_is_from_upload_to_the_first_rated_result(f, db):
    ada, bob = f.player("ada"), f.player("bob")
    a = f.version(ada, "a", 5)
    b = f.version(bob, "b", 10)
    f.match((a, b), finished=2)
    f.match((a, b), finished=1)
    f.match((b, a), kind="comparison", finished=9)  # unrated: not a first match
    first = metrics.usage(db, RATINGS, SETTINGS).seconds_to_first_match
    assert first.n == 2
    assert first.p50 == pytest.approx(3 * 3600, abs=1)
    assert first.p95 == pytest.approx(8 * 3600, abs=1)


def test_sandbox_outcomes_are_shares_of_rated_matches(f, db):
    ada, bob = f.player("ada"), f.player("bob")
    a, b = f.version(ada, "a", 5), f.version(bob, "b", 5)
    for reason in ("timeout", "crash", "core_destroyed", "core_destroyed"):
        f.match((a, b), reason=reason)
    f.match((a, b), kind="comparison", reason="memory")
    stats = metrics.usage(db, RATINGS, SETTINGS)
    assert stats.rated_matches == 4
    assert stats.sandbox_outcomes == {
        "timeout": 0.25,
        "crash": 0.25,
        "memory": 0.0,
        "invalid_output": 0.0,
        "both_failed": 0.0,
    }


def test_health_reports_errors_durations_queue_and_utilisation(f, db, store):
    ada, bob = f.player("ada"), f.player("bob")
    a, b = f.version(ada, "a", 5), f.version(bob, "b", 5)
    f.match((a, b), created=3, started=2, finished=1.5)
    f.match((a, b), status="void", started=1, finished=1, void_reason="platform_error: boom")
    f.match((a, b), status="void", started=1, finished=0.5, void_reason="lease expired")
    f.match((a, b), status="queued", created=2, started=None, finished=None)
    f.match((a, b), created=50, started=49, finished=48)  # outside the 24 h window
    store.root.mkdir(parents=True)
    report = metrics.health(db, store, SETTINGS)
    assert (report.matches_finished, report.platform_errors, report.lease_expired) == (1, 1, 1)
    assert report.platform_error_rate == pytest.approx(1 / 3)
    assert report.end_reasons == {"core_destroyed": 1}
    assert report.match_seconds.p50 == pytest.approx(1800, abs=1)
    assert report.queue_depth == 1
    assert report.oldest_queued_s == pytest.approx(7200, abs=2)
    assert report.queue_wait_s.n == 3  # every match that started in the window
    assert report.worker_utilisation == pytest.approx(1800 / (24 * 3600), abs=1e-4)
    assert any("platform errors" in a for a in report.alerts)
    assert any("waited 120 min" in a for a in report.alerts)


def test_alerts_cover_disk_pause_and_egress_and_stay_quiet_when_all_is_well(db, data, monkeypatch):
    store = Store(data)
    assert metrics.health(db, store, SETTINGS).alerts == []
    full = SimpleNamespace(total=100, used=81, free=19)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: full)
    ops.pause(data, "testing")
    (data / "EGRESS_CAPPED").write_text("")
    alerts = metrics.health(db, store, SETTINGS).alerts
    assert alerts == [
        "disk 81% full",
        f"ladder paused: {(data / 'PAUSED').read_text().strip()}",
        "site off: this month's egress budget is spent",
    ]


@pytest.fixture
def data(tmp_path):
    ops.bootstrap(tmp_path / "data")
    return tmp_path / "data"


def test_the_guard_pings_the_uptime_checker_and_reports_failures(data):
    sent: list[httpx.Request] = []
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: sent.append(r) or httpx.Response(200))
    )
    url = "https://hc-ping.example/uuid"
    assert ops.report_alerts(Store(data), SETTINGS, url, client) == []
    ops.pause(data, "testing")
    assert ops.report_alerts(Store(data), SETTINGS, url, client)
    assert [str(r.url) for r in sent] == [url, f"{url}/fail"]
    assert b"ladder paused" in sent[1].content
