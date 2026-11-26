"""The worker: a match becomes a result only with a stored, reproducible replay, and anything
that goes wrong on the platform's side voids it."""

import os
import signal
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import plays
from arena.replay import load
from arena_server import bots, queue
from arena_server.settings import Settings
from arena_server.store import REPLAY, REPLAYS
from arena_server.worker import Worker
from helpers import must_claim

TESTS = Path(__file__).parent
SLOW_BOT = b"""
import time
from arena import Bot

class Slow(Bot):
    def act(self, obs):
        time.sleep(0.2)
        return []
"""
BROKEN_BOT = b"""
from arena import Bot

class Broken(Bot):
    def act(self, obs):
        raise ValueError("the bug is on line 6")
"""
FINE_BOT = b"""
from arena import Bot

class Fine(Bot):
    def act(self, obs):
        return []
"""


def result_and_status(db, match_id):
    row = db.execute(
        """SELECT m.status, m.void_reason, r.end_reason, r.replay_sha256
           FROM matches m LEFT JOIN results r ON r.match_id = m.id WHERE m.id = ?""",
        (match_id,),
    ).fetchone()
    return tuple(row)


def test_a_match_is_played_recorded_and_replayable(db, store):
    match = queue.enqueue(
        db,
        "ranked",
        (bots.builtin_version(db, "rush"), bots.builtin_version(db, "greedy")),
        seed=11,
    )
    assert Worker(db, store, plays.local).step()
    status, _, reason, replay = result_and_status(db, match)
    assert (status, reason) == ("done", "core_destroyed")
    assert load(store.path(REPLAYS, replay, REPLAY)).data["seed"] == 11


def test_a_platform_error_voids_the_match_and_never_rates_it(db, store):
    match = queue.enqueue(
        db, "ranked", (bots.builtin_version(db, "rush"), bots.builtin_version(db, "greedy")), seed=1
    )

    def broken_platform(players, seed, rules):
        raise OSError("disk full")

    Worker(db, store, broken_platform).step()
    status, reason, result, _ = result_and_status(db, match)
    assert (status, result) == ("void", None)
    assert reason.startswith("platform_error") and "disk full" in reason


def test_a_replay_that_does_not_reproduce_is_never_rated(db, store):
    match = queue.enqueue(
        db, "ranked", (bots.builtin_version(db, "rush"), bots.builtin_version(db, "greedy")), seed=2
    )

    def tampered(players, seed, rules):
        record = plays.local(players, seed, rules)
        record.orders[0] = ([], [])  # the stored orders no longer lead to the final state
        return record

    Worker(db, store, tampered).step()
    status, reason, result, _ = result_and_status(db, match)
    assert (status, result) == ("void", None)
    assert "does not reproduce" in reason


def test_a_match_queued_for_another_engine_is_voided(db, store):
    match = queue.enqueue(
        db, "ranked", (bots.builtin_version(db, "rush"), bots.builtin_version(db, "greedy")), seed=3
    )
    db.execute("UPDATE matches SET engine_version = '0.0.1' WHERE id = ?", (match,))
    Worker(db, store, plays.local).step()
    assert result_and_status(db, match)[:3] == (
        "void",
        "platform_error: RuntimeError('queued for engine 0.0.1')",
        None,
    )


def test_validation_activates_a_working_bot_and_retires_its_old_version(db, store):
    owner = bots.ensure_user(db, "ada", github_id=1)
    bot = bots.create_bot(db, owner, "mine")
    first = bots.submit_version(db, store, bot, FINE_BOT)
    worker = Worker(db, store, plays.local)
    worker.step()
    second = bots.submit_version(db, store, bot, FINE_BOT + b"\n# v2\n")
    worker.step()
    statuses = dict(db.execute("SELECT id, status FROM bot_versions WHERE bot_id = ?", (bot,)))
    assert statuses == {first: "retired", second: "active"}


def test_validation_rejects_a_broken_bot_and_tells_its_owner_why(db, store):
    owner = bots.ensure_user(db, "bob", github_id=2)
    version = bots.submit_version(db, store, bots.create_bot(db, owner, "oops"), BROKEN_BOT)
    Worker(db, store, plays.local).step()
    status, error = db.execute(
        "SELECT status, error FROM bot_versions WHERE id = ?", (version,)
    ).fetchone()
    assert status == "rejected"
    assert error.startswith("crash") and "the bug is on line 6" in error


def test_identical_uploads_are_stored_once(db, store):
    owner = bots.ensure_user(db, "cy", github_id=3)
    a = bots.submit_version(db, store, bots.create_bot(db, owner, "a"), FINE_BOT)
    b = bots.submit_version(db, store, bots.create_bot(db, owner, "b"), FINE_BOT)
    codes = {r[0] for r in db.execute("SELECT code FROM bot_versions WHERE id IN (?, ?)", (a, b))}
    assert len(codes) == 1


def test_killing_a_worker_mid_match_voids_it_and_queues_it_again(tmp_path, db, store):
    owner = bots.ensure_user(db, "dee", github_id=4)
    slow = bots.submit_version(db, store, bots.create_bot(db, owner, "slow"), SLOW_BOT)
    bots.activate(db, slow)
    greedy = bots.builtin_version(db, "greedy")
    match = queue.enqueue(db, "ranked", (slow, greedy), seed=5)

    env = {**os.environ, "PYTHONPATH": str(TESTS)}
    worker = subprocess.Popen(
        [
            sys.executable,
            str(TESTS / "worker_once.py"),
            str(tmp_path / "arena.db"),
            str(store.root),
        ],
        env=env,
    )
    deadline = time.monotonic() + 20
    while result_and_status(db, match)[0] != "running":
        assert time.monotonic() < deadline, "the worker never claimed the match"
        time.sleep(0.05)
    time.sleep(0.5)  # mid-match
    os.kill(worker.pid, signal.SIGKILL)
    worker.wait()

    lease = Settings.load().lease_s
    [again] = queue.reap(db, now=time.time() + lease + 1)
    assert result_and_status(db, match) == ("void", "lease expired", None, None)
    assert db.execute("SELECT count(*) FROM results").fetchone()[0] == 0
    retry = must_claim(db, "next", 60)
    assert (retry.match_id, retry.seed, retry.version_ids) == (again, 5, (slow, greedy))


def test_settings_cover_the_slowest_possible_match():
    from arena.limits import Limits
    from arena_engine import Rules

    limits = Limits.load()
    slowest = Rules().max_turns * limits.turn_backstop_ms / 1000 + limits.init_ms / 1000
    assert Settings.load().lease_s > slowest
    assert replace(Settings.load()) == Settings.load()
