"""The match queue is the matches table (ADR-004). A claim is one atomic UPDATE; a lease lets
the reaper recover a dead worker's match without ever rating it."""

import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from arena.runner import Result
from arena_engine import ENGINE_VERSION


@contextmanager
def immediate(conn: sqlite3.Connection) -> Iterator[None]:
    """A write transaction that takes the lock up front, so two workers can't both read the
    same queued row before either updates it."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


@dataclass(frozen=True)
class Claim:
    match_id: int
    seed: int
    engine_version: str
    version_ids: tuple[int, int]
    codes: tuple[str, str]  # "sha256:..." in the code store, or "builtin:NAME"


def enqueue(
    conn: sqlite3.Connection, kind: str, version_ids: tuple[int, int], seed: int, priority: int = 0
) -> int:
    with immediate(conn):
        return _insert(conn, kind, version_ids, seed, priority)


def claim(conn: sqlite3.Connection, worker_id: str, lease_s: float) -> Claim | None:
    with immediate(conn):
        row = conn.execute(
            """UPDATE matches SET status = 'running', worker_id = ?, lease_until = ?
               WHERE id = (SELECT id FROM matches WHERE status = 'queued'
                           ORDER BY priority DESC, id LIMIT 1)
               RETURNING id, seed, engine_version""",
            (worker_id, time.time() + lease_s),
        ).fetchone()
        if row is None:
            return None
        players = conn.execute(
            """SELECT bv.id, bv.code FROM match_players mp
               JOIN bot_versions bv ON bv.id = mp.bot_version_id
               WHERE mp.match_id = ? ORDER BY mp.seat""",
            (row["id"],),
        ).fetchall()
    return Claim(
        row["id"],
        row["seed"],
        row["engine_version"],
        (players[0]["id"], players[1]["id"]),
        (players[0]["code"], players[1]["code"]),
    )


def finish(
    conn: sqlite3.Connection, match_id: int, worker_id: str, result: Result, replay: str
) -> bool:
    """Record a result, but only while this worker still holds a live lease on the match. A
    reaped or voided match can never gain a result."""
    with immediate(conn):
        updated = conn.execute(
            """UPDATE matches SET status = 'done', finished_at = datetime('now')
               WHERE id = ? AND status = 'running' AND worker_id = ? AND lease_until >= ?""",
            (match_id, worker_id, time.time()),
        ).rowcount
        if updated != 1:
            return False
        conn.execute(
            """INSERT INTO results (match_id, winner_seat, end_reason, turns, replay_sha256)
               VALUES (?, ?, ?, ?, ?)""",
            (match_id, result.winner, result.reason, result.turns, replay),
        )
    return True


def void(conn: sqlite3.Connection, match_id: int, reason: str) -> None:
    with immediate(conn):
        conn.execute(
            """UPDATE matches SET status = 'void', void_reason = ?, finished_at = datetime('now')
               WHERE id = ? AND status IN ('queued', 'running')""",
            (reason, match_id),
        )


def reap(conn: sqlite3.Connection, now: float | None = None) -> list[int]:
    """Void running matches whose lease has expired and queue each pairing again, same seed.
    Returns the new match ids."""
    now = time.time() if now is None else now
    with immediate(conn):
        expired = conn.execute(
            """SELECT id, kind, seed, priority FROM matches
               WHERE status = 'running' AND lease_until < ?""",
            (now,),
        ).fetchall()
        requeued = []
        for m in expired:
            conn.execute(
                """UPDATE matches SET status = 'void', void_reason = 'lease expired',
                   finished_at = datetime('now') WHERE id = ?""",
                (m["id"],),
            )
            players = conn.execute(
                "SELECT bot_version_id FROM match_players WHERE match_id = ? ORDER BY seat",
                (m["id"],),
            ).fetchall()
            pair = (players[0][0], players[1][0])
            requeued.append(_insert(conn, m["kind"], pair, m["seed"], m["priority"]))
    return requeued


def _insert(
    conn: sqlite3.Connection, kind: str, version_ids: tuple[int, int], seed: int, priority: int
) -> int:
    match_id = conn.execute(
        """INSERT INTO matches (kind, seed, engine_version, priority)
           VALUES (?, ?, ?, ?) RETURNING id""",
        (kind, seed, ENGINE_VERSION, priority),
    ).fetchone()[0]
    conn.executemany(
        "INSERT INTO match_players (match_id, seat, bot_version_id) VALUES (?, ?, ?)",
        [(match_id, seat, v) for seat, v in enumerate(version_ids)],
    )
    return match_id
