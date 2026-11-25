"""Matches with real bot processes: normal play, every way a bot can fail, and parity
between a bot run as a subprocess and the same bot run in-process."""

import textwrap
from dataclasses import replace
from pathlib import Path

import pytest
from arena.limits import Limits
from arena.replay import ReplayError, load, save
from arena.runner import run_match
from arena_engine import ENGINE_VERSION, state_hash

QUICK = replace(Limits.load(), local_backstop_ms=1500)


def bot_file(tmp_path: Path, body: str, name: str = "bot.py") -> str:
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


HOLDS = """
    from arena import Bot

    class Holds(Bot):
        def act(self, obs):
            return []
"""


def test_a_subprocess_bot_plays_a_full_match(tmp_path):
    record = run_match((bot_file(tmp_path, HOLDS), "builtin:greedy"), seed=3)
    assert record.result.winner == 1
    assert record.result.turns > 0
    assert record.stderr == ("", "")


def test_a_bot_in_a_subprocess_plays_exactly_as_it_does_in_process(tmp_path):
    clone = bot_file(
        tmp_path,
        """
        from arena.builtin.scout import ScoutBot

        class Clone(ScoutBot):
            pass
        """,
    )
    inside = run_match(("builtin:scout", "builtin:rush"), seed=21)
    outside = run_match((clone, "builtin:rush"), seed=21)
    assert outside.orders == inside.orders
    assert outside.logs == inside.logs
    assert outside.result == inside.result


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("raise RuntimeError('boom')", "crash"),
        ("import sys; sys.exit(3)", "crash"),
        ("return 'not a list'", "crash"),
        ("import time; time.sleep(30)", "timeout"),
    ],
)
def test_a_failing_bot_loses_and_the_match_still_ends(tmp_path, body, reason):
    path = bot_file(
        tmp_path,
        f"""
        from arena import Bot

        class Fails(Bot):
            def act(self, obs):
                if obs.turn == 2:
                    {body}
                return []
        """,
    )
    record = run_match(("builtin:greedy", path), seed=4, limits=QUICK)
    assert (record.result.winner, record.result.reason, record.result.turns) == (0, reason, 2)
    assert len(record.orders) == 2  # turns 0 and 1 happened; turn 2 never resolved


def test_a_crash_shows_its_traceback_to_the_owner(tmp_path):
    path = bot_file(
        tmp_path,
        """
        from arena import Bot

        class Fails(Bot):
            def act(self, obs):
                raise RuntimeError("the bug is here")
        """,
    )
    record = run_match((path, "builtin:greedy"), seed=4, limits=QUICK)
    assert "the bug is here" in record.stderr[0]


def test_printing_never_corrupts_the_protocol(tmp_path):
    path = bot_file(
        tmp_path,
        """
        import os
        from arena import Bot

        print("at import time")

        class Chatty(Bot):
            def act(self, obs):
                print("turn", obs.turn, '{"t": "orders"}')
                self.log("also logged")
                if obs.turn == 1:
                    os.write(1, b"straight to file descriptor 1\\n")
                return []
        """,
    )
    record = run_match((path, "builtin:greedy"), seed=5)
    assert record.result.reason != "invalid_output"
    turn, text = record.logs[0][1]
    assert (turn, text) == (1, 'turn 1 {"t": "orders"}\nalso logged\n')
    assert "at import time" in record.stderr[0]
    assert "straight to file descriptor 1" in record.stderr[0]


def test_both_bots_failing_together_is_a_draw(tmp_path):
    path = bot_file(
        tmp_path,
        """
        from arena import Bot

        class Fails(Bot):
            def act(self, obs):
                raise RuntimeError
        """,
    )
    record = run_match((path, path), seed=1, limits=QUICK)
    assert (record.result.winner, record.result.reason) == (None, "both_failed")


def test_slow_turns_are_reported_as_warnings(tmp_path):
    path = bot_file(
        tmp_path,
        """
        import time
        from arena import Bot

        class Slow(Bot):
            def act(self, obs):
                if obs.turn < 3:
                    time.sleep(0.15)
                return []
        """,
    )
    record = run_match((path, "builtin:rush"), seed=2)
    assert any("turns over the 100 ms budget" in w for w in record.warnings)


def test_replays_round_trip_and_reproduce(tmp_path):
    record = run_match(("builtin:scout", "builtin:turtle"), seed=8)
    path = tmp_path / "replay.json.gz"
    save(record, path)
    replay = load(path)
    assert replay.data["engine_version"] == ENGINE_VERSION
    assert record.final_state is not None
    assert state_hash(replay.states[-1]) == state_hash(record.final_state)
    assert len(replay.states) == len(record.orders) + 1


def test_a_forfeited_match_still_replays(tmp_path):
    path = bot_file(
        tmp_path,
        """
        from arena import Bot

        class Fails(Bot):
            def act(self, obs):
                if obs.turn == 30:
                    raise RuntimeError
                return []
        """,
    )
    record = run_match(("builtin:rush", path), seed=6, limits=QUICK)
    out = tmp_path / "replay.json.gz"
    save(record, out)
    assert len(load(out).states) == 31


def test_a_tampered_replay_is_rejected(tmp_path):
    import gzip
    import json

    record = run_match(("builtin:greedy", "builtin:rush"), seed=8)
    out = tmp_path / "replay.json.gz"
    save(record, out)
    data = json.loads(gzip.decompress(out.read_bytes()))
    data["turns"][5]["orders"][0] = []
    out.write_bytes(gzip.compress(json.dumps(data).encode()))
    with pytest.raises(ReplayError, match="does not reproduce"):
        load(out)
