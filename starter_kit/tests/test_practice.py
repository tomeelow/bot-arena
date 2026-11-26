"""Browser practice drives the same `Match` as the CLI: same seed and bots, same replay."""

import json
import time
from pathlib import Path

import pytest
from arena.practice import PlayerBot, Practice
from arena.replay import decode, to_dict
from arena.runner import run_match

EXAMPLE = Path(__file__).parents[1] / "examples" / "first_bot.py"


def play(path: Path, opponent: str, seed: int, seat: int) -> Practice:
    """What the page's JavaScript does, with both workers in this process."""
    practice = Practice(str(path), opponent, seed, seat)
    bot = PlayerBot(str(path))
    while (line := practice.to_player()) is not None:
        start = time.perf_counter()
        reply = bot.answer(line)
        ms = (time.perf_counter() - start) * 1000
        problem = "" if reply is not None else "crash"
        practice.from_player(reply, ms, problem, "" if reply else "the bot raised an exception")
    return practice


def canonical(data: dict) -> dict:
    """A replay minus what may differ between runs: thinking times."""
    turns = [{"orders": t["orders"]} for t in data["turns"]]
    return {**data, "turns": turns}


@pytest.mark.parametrize("seat", [0, 1])
def test_practice_records_the_replay_the_cli_records(seat):
    practice = play(EXAMPLE, "builtin:greedy", seed=3, seat=seat)
    players = ("builtin:greedy", str(EXAMPLE)) if seat else (str(EXAMPLE), "builtin:greedy")
    cli = run_match(players, 3)
    assert canonical(decode(practice.replay()).data) == canonical(to_dict(cli))


def test_frames_cover_every_turn_and_the_end_is_reported():
    practice = play(EXAMPLE, "builtin:random", seed=1, seat=0)
    frames = json.loads(practice.take_frames())
    summary = json.loads(practice.finish(""))
    assert [f["turn"] for f in frames] == list(range(summary["end"]["turns"] + 1))
    assert practice.header["players"][0] == {"seat": 0, "bot": "first_bot", "owner": "you"}


def test_a_bot_that_fails_to_import_loses_with_its_traceback(tmp_path):
    broken = tmp_path / "broken.py"
    broken.write_text("raise RuntimeError('oops')\n")
    bot = PlayerBot(str(broken))
    assert bot.answer('{"t": "init"}') is None
    assert "RuntimeError: oops" in bot.error
    practice = play(broken, "builtin:random", seed=1, seat=1)
    summary = json.loads(practice.finish(bot.error))
    assert summary["end"] == {"type": "end", "winner": 0, "reason": "crash", "turns": 0}
