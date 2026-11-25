"""Swapping seats plays the mirror-image game (GAME_RULES.md §8): seat order never matters."""

from engine_support import RandomBot, play, swap_seats
from hypothesis import given, settings
from hypothesis import strategies as st

from arena_engine import state_hash


@settings(max_examples=8, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=2**32),
    bot_a=st.integers(min_value=0, max_value=1000),
    bot_b=st.integers(min_value=0, max_value=1000),
)
def test_seat_swap_mirrors_the_whole_game(seed, bot_a, bot_b):
    g1 = play((RandomBot(bot_a), RandomBot(bot_b)), seed, turns=400)
    g2 = play((RandomBot(bot_b), RandomBot(bot_a)), seed, turns=400)
    assert len(g1.states) == len(g2.states)
    for a, b in zip(g1.states, g2.states, strict=True):
        assert state_hash(swap_seats(a)) == state_hash(b)
    for (a0, a1), (b0, b1) in zip(g1.events, g2.events, strict=True):
        assert (a0, a1) == (b1, b0)
