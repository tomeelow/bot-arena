"""GAME_RULES.md §8 invariants, checked after every turn of many random games."""

from collections import Counter

from engine_support import RandomBot, crystal_total, play
from hypothesis import given, settings
from hypothesis import strategies as st

from arena_engine import UNIT_STATS, GameState
from arena_engine.geometry import in_bounds


def broken_invariants(state: GameState, initial_crystals: int) -> list[str]:
    problems: list[str] = []
    blocked = set(state.walls) | {d.pos for d in state.deposits} | {c.pos for c in state.cores}
    cells = Counter(u.pos for u in state.units)
    if any(n > 1 for n in cells.values()):
        problems.append("two units share a cell")
    for u in state.units:
        stats = UNIT_STATS[u.kind]
        if u.pos in blocked or not in_bounds(u.pos, state.rules):
            problems.append(f"{u} stands where no unit may stand")
        if not 0 < u.hp <= stats.hp or not 0 <= u.cargo <= stats.carry:
            problems.append(f"{u} has impossible hp or cargo")
        if u.id >= state.next_id[u.seat]:
            problems.append(f"{u} has an id that was never issued")
    for seat in (0, 1):
        ids = [u.id for u in state.units if u.seat == seat]
        if len(ids) != len(set(ids)) or len(ids) > state.rules.max_units:
            problems.append(f"seat {seat} has duplicate ids or too many units")
    if min(state.banks) < 0 or any(d.amount < 0 for d in state.deposits):
        problems.append("negative crystals")
    if crystal_total(state) != initial_crystals:
        problems.append(f"crystals not conserved: {crystal_total(state)} != {initial_crystals}")
    return problems


@settings(max_examples=25, deadline=None)
@given(
    seed=st.integers(min_value=0, max_value=2**32),
    bot_a=st.integers(min_value=0, max_value=1000),
    bot_b=st.integers(min_value=0, max_value=1000),
)
def test_invariants_hold_every_turn(seed, bot_a, bot_b):
    game = play((RandomBot(bot_a), RandomBot(bot_b)), seed, turns=400)
    initial = crystal_total(game.states[0])
    for state in game.states:
        assert broken_invariants(state, initial) == [], f"turn {state.turn}"
