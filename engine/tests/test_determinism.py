"""Same seed + same orders = same game, in any process, whatever the hash seed."""

import os
import subprocess
import sys
from pathlib import Path

from engine_support import RandomBot, play
from hypothesis import given, settings
from hypothesis import strategies as st

from arena_engine import Rules, state_hash, step

SUPPORT = Path(__file__).parent
SCRIPT = """
from engine_support import RandomBot, play
from arena_engine import state_hash
print(state_hash(play((RandomBot(1), RandomBot(2)), seed=11, turns=150).states[-1]))
"""


@settings(max_examples=10, deadline=None)
@given(st.integers(min_value=0, max_value=2**32))
def test_replaying_the_orders_reproduces_every_state(seed):
    game = play((RandomBot(seed), RandomBot(seed + 1)), seed, turns=120)
    state = game.states[0]
    for orders, expected in zip(game.orders, game.states[1:], strict=True):
        state = step(state, {0: orders[0], 1: orders[1]}).state
        assert state_hash(state) == state_hash(expected)


def test_hash_seed_does_not_change_the_game():
    results = set()
    for hash_seed in ("0", "1", "4242"):
        env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONPATH": str(SUPPORT)}
        out = subprocess.run(
            [sys.executable, "-c", SCRIPT], env=env, capture_output=True, text=True, check=True
        )
        results.add(out.stdout.strip())
    assert len(results) == 1


def test_bots_with_different_seeds_play_different_games():
    a = play((RandomBot(1), RandomBot(2)), seed=5, turns=50).states[-1]
    b = play((RandomBot(3), RandomBot(4)), seed=5, turns=50).states[-1]
    assert state_hash(a) != state_hash(b)
    assert a.rules == b.rules == Rules()
