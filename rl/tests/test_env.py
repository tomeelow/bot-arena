"""The training environment plays the same game the CLI runner does."""

import pytest
from arena.harness import load_bot
from arena.runner import run_match
from arena_engine import Rules, observe
from arena_rl.env import ArenaEnv, play

PAIRS = [("rush", "scout"), ("turtle", "greedy"), ("random", "rush")]


@pytest.mark.parametrize(("a", "b"), PAIRS)
@pytest.mark.parametrize("seed", [0, 7])
def test_play_gives_the_cli_runners_result_and_final_state(a, b, seed):
    record = run_match((f"builtin:{a}", f"builtin:{b}"), seed)
    result, state = play((load_bot(f"builtin:{a}")(), load_bot(f"builtin:{b}")()), seed)
    assert result == record.result
    assert state == record.final_state


def test_observations_are_the_engines_observe():
    env = ArenaEnv(Rules())
    obs = env.reset(3)
    assert obs == (observe(env.state, 0), observe(env.state, 1))
