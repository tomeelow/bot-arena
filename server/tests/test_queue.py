"""The queue: atomic claims, results only under a live lease, and recovery from dead workers."""

import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import plays
from arena.replay import load
from arena.runner import Result
from arena_server import bots, queue
from arena_server.db import connect, migrate
from arena_server.ratings import Ratings
from arena_server.settings import Settings
from arena_server.store import REPLAY, REPLAYS, Store
from arena_server.worker import Worker
from helpers import must_claim

DRAW = Result(None, "turn_limit", 5)
RATINGS = Ratings(Settings.load())


def pair(db):
    return (bots.builtin_version(db, "random"), bots.builtin_version(db, "greedy"))


def test_migrations_apply_once(db):
    assert migrate(db) == 1
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"users", "bots", "bot_versions", "matches", "match_players", "results"} <= tables


def test_claims_take_the_highest_priority_then_the_oldest(db):
    versions = pair(db)
    low = queue.enqueue(db, "ranked", versions, seed=1)
    high = queue.enqueue(db, "placement", versions, seed=2, priority=5)
    assert must_claim(db, "w", 60).match_id == high
    assert must_claim(db, "w", 60).match_id == low
    assert queue.claim(db, "w", 60) is None


def test_a_claim_carries_the_players_in_seat_order(db):
    versions = pair(db)
    queue.enqueue(db, "ranked", versions, seed=9)
    claim = must_claim(db, "w", 60)
    assert (claim.seed, claim.version_ids) == (9, versions)
    assert claim.codes == ("builtin:random", "builtin:greedy")


def test_a_result_needs_this_workers_live_lease(db):
    queue.enqueue(db, "ranked", pair(db), seed=1)
    claim = must_claim(db, "w1", 60)
    assert not queue.finish(db, claim.match_id, "w2", DRAW, "sha256:x", RATINGS)
    queue.enqueue(db, "ranked", pair(db), seed=2)
    expired = must_claim(db, "w1", -1)
    assert not queue.finish(db, expired.match_id, "w1", DRAW, "sha256:x", RATINGS)
    assert db.execute("SELECT count(*) FROM results").fetchone()[0] == 0
    assert queue.finish(db, claim.match_id, "w1", DRAW, "sha256:x", RATINGS)


def test_reaping_voids_an_expired_match_and_queues_the_pairing_again(db):
    versions = pair(db)
    queue.enqueue(db, "placement", versions, seed=7, priority=3)
    stale = must_claim(db, "dead", -1)
    [again] = queue.reap(db)
    old = db.execute("SELECT status, void_reason FROM matches WHERE id = ?", (stale.match_id,))
    assert tuple(old.fetchone()) == ("void", "lease expired")
    retry = must_claim(db, "alive", 60)
    assert (retry.match_id, retry.seed, retry.version_ids) == (again, 7, versions)
    assert not queue.finish(db, stale.match_id, "dead", DRAW, "sha256:x", RATINGS)


def drain(db_path: Path, data: Path) -> int:
    worker = Worker(connect(db_path), Store(data), plays.quick, worker_id=f"w{os.getpid()}")
    played = 0
    while worker.step():
        played += 1
    return played


def test_eight_workers_play_five_hundred_matches_exactly_once(tmp_path, db, store):
    versions = pair(db)
    for seed in range(500):
        queue.enqueue(db, "ranked", versions if seed % 2 else (versions[1], versions[0]), seed)
    with ProcessPoolExecutor(8) as pool:
        counts = list(pool.map(drain, [tmp_path / "arena.db"] * 8, [store.root] * 8))
    assert sum(counts) == 500
    assert sum(c > 0 for c in counts) > 1
    statuses = dict(db.execute("SELECT status, count(*) FROM matches GROUP BY status").fetchall())
    assert statuses == {"done": 500}
    workers = db.execute("SELECT count(DISTINCT worker_id) FROM matches").fetchone()[0]
    assert workers > 1
    replays = [r[0] for r in db.execute("SELECT replay_sha256 FROM results")]
    assert len(replays) == 500
    for ref in set(replays):
        load(store.path(REPLAYS, ref, REPLAY))  # every stored replay re-simulates to its hash
