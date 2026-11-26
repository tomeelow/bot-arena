"""The ladder: who plays whom, and the standings.

Pairings go to the bot with the most left to learn (the widest sigma), against an opponent
chosen with a preference for close games, with a floor so lopsided ones still happen. Every
pairing is played from both seats on the same seed. Bots from the same owner never meet.
"""

import sqlite3
from collections import Counter
from dataclasses import dataclass
from random import Random

from .bots import ARENA_ACCOUNT
from .queue import enqueue
from .ratings import Rating, Ratings, stored
from .settings import Settings


@dataclass(frozen=True)
class Entry:
    version_id: int
    owner_id: int
    handle: str
    bot_id: int
    bot: str
    rating: Rating
    pending: int  # queued or running matches


@dataclass(frozen=True)
class Standing:
    rank: int
    entry: Entry
    score: float  # mu - k sigma: what the ladder sorts by
    provisional: bool


def entries(conn: sqlite3.Connection, ratings: Ratings) -> list[Entry]:
    """Every active version with its rating (the prior if it hasn't played yet)."""
    table = stored(conn)
    pending = Counter(
        row[0]
        for row in conn.execute(
            """SELECT mp.bot_version_id FROM match_players mp
               JOIN matches m ON m.id = mp.match_id WHERE m.status IN ('queued', 'running')"""
        )
    )
    rows = conn.execute(
        """SELECT v.id, v.parent_id, b.owner_id, u.handle, b.id AS bot_id, b.name
           FROM bot_versions v
           JOIN bots b ON b.id = v.bot_id JOIN users u ON u.id = b.owner_id
           WHERE v.status = 'active' ORDER BY v.id"""
    ).fetchall()
    return [
        Entry(
            r["id"],
            r["owner_id"],
            r["handle"],
            r["bot_id"],
            r["name"],
            table.get(r["id"]) or ratings.prior(table.get(r["parent_id"])),
            pending[r["id"]],
        )
        for r in rows
    ]


def leaderboard(conn: sqlite3.Connection, ratings: Ratings) -> list[Standing]:
    ranked = sorted(entries(conn, ratings), key=lambda e: -ratings.conservative(e.rating))
    return [
        Standing(i, e, ratings.conservative(e.rating), ratings.provisional(e.rating))
        for i, e in enumerate(ranked, start=1)
    ]


def next_pairing(
    conn: sqlite3.Connection, ratings: Ratings, settings: Settings, rng: Random
) -> tuple[int, int] | None:
    pool = entries(conn, ratings)
    recent = _recent_pairs(conn, settings.pair_window)
    # Most to learn first; games already queued count as learning in progress.
    for bot in sorted(pool, key=lambda e: (-(e.rating.sigma - 0.5 * e.pending), e.version_id)):
        candidates = [
            c
            for c in pool
            if c.owner_id != bot.owner_id
            and recent[frozenset((bot.version_id, c.version_id))] < settings.pair_cap
        ]
        if candidates:
            weights = [pairing_weight(ratings, settings, bot.rating, c.rating) for c in candidates]
            return bot.version_id, rng.choices(candidates, weights)[0].version_id
    return None


def pairing_weight(ratings: Ratings, settings: Settings, a: Rating, b: Rating) -> float:
    """1 for an even game, falling towards 0 as it gets lopsided, never below the floor."""
    return max(1 - abs(2 * ratings.p_win(a, b) - 1), settings.explore_floor)


def schedule(
    conn: sqlite3.Connection, pair: tuple[int, int], kind: str, rng: Random, priority: int = 0
) -> list[int]:
    """Queue a pairing from both seats on one seed: seat and map luck cancel out."""
    seed = rng.randrange(2**31)
    a, b = pair
    return [
        enqueue(conn, kind, (a, b), seed, priority),
        enqueue(conn, kind, (b, a), seed, priority),
    ]


def place(conn: sqlite3.Connection, version_id: int, settings: Settings, rng: Random) -> list[int]:
    """A new version's first games: against every built-in anchor, so it lands near its level
    quickly. Anchors never leave the ladder, which pins the rating scale over time."""
    anchors = conn.execute(
        """SELECT v.id FROM bot_versions v JOIN bots b ON b.id = v.bot_id
           JOIN users u ON u.id = b.owner_id
           WHERE u.handle = ? AND v.status = 'active' AND v.id != ? ORDER BY v.id""",
        (ARENA_ACCOUNT, version_id),
    ).fetchall()
    owner = _owner(conn, version_id)
    matches = []
    for (anchor,) in anchors:
        if _owner(conn, anchor) == owner:
            continue
        for _ in range(settings.placement_seed_pairs):
            matches += schedule(
                conn, (version_id, anchor), "placement", rng, settings.placement_priority
            )
    return matches


def top_up(
    conn: sqlite3.Connection, ratings: Ratings, settings: Settings, rng: Random
) -> list[int]:
    """Keep about `queue_target` matches queued, so workers never sit idle."""
    queued = conn.execute("SELECT count(*) FROM matches WHERE status = 'queued'").fetchone()[0]
    added: list[int] = []
    while queued + len(added) < settings.queue_target:
        pair = next_pairing(conn, ratings, settings, rng)
        if pair is None:
            break
        added += schedule(conn, pair, "ranked", rng)
    return added


def _recent_pairs(conn: sqlite3.Connection, window: int) -> Counter[frozenset[int]]:
    rows = conn.execute(
        """SELECT p0.bot_version_id, p1.bot_version_id FROM matches m
           JOIN match_players p0 ON p0.match_id = m.id AND p0.seat = 0
           JOIN match_players p1 ON p1.match_id = m.id AND p1.seat = 1
           WHERE m.status != 'void' ORDER BY m.id DESC LIMIT ?""",
        (window,),
    ).fetchall()
    return Counter(frozenset(r) for r in rows)


def _owner(conn: sqlite3.Connection, version_id: int) -> int:
    return conn.execute(
        "SELECT b.owner_id FROM bot_versions v JOIN bots b ON b.id = v.bot_id WHERE v.id = ?",
        (version_id,),
    ).fetchone()[0]
