"""Generated maps: symmetric, connected, and laid out as GAME_RULES.md §2 says."""

import pytest
from engine_support import swap_seats

from arena_engine import GameState, Kind, Pos, Rules, new_game, state_hash
from arena_engine.geometry import DIRS, dist2, in_bounds, step_pos

RULES = Rules()
SEEDS = range(1000)


def check_map(state: GameState) -> list[str]:
    """Every §2 property that fails for this map."""
    rules = state.rules
    problems: list[str] = []
    if state_hash(swap_seats(state)) != state_hash(state):
        problems.append("not 180° symmetric")
    blocked = set(state.walls) | {d.pos for d in state.deposits} | {c.pos for c in state.cores}
    open_cells = {
        p
        for y in range(rules.height)
        for x in range(rules.width)
        if (p := Pos(x, y)) not in blocked
    }
    start = next(n for d in DIRS if (n := step_pos(state.cores[0].pos, d)) in open_cells)
    reached, frontier = {start}, [start]
    while frontier:
        p = frontier.pop()
        for d in DIRS:
            n = step_pos(p, d)
            if n in open_cells and n not in reached:
                reached.add(n)
                frontier.append(n)
    if reached != open_cells:
        problems.append("some open cells are unreachable")
    for site in [c.pos for c in state.cores] + [d.pos for d in state.deposits]:
        if not any(in_bounds(n := step_pos(site, d), rules) and n in reached for d in DIRS):
            problems.append(f"{site} has no reachable neighbour")
    for core in state.cores:
        home = [d for d in state.deposits if 9 <= dist2(d.pos, core.pos) <= 25]
        if len(home) < rules.home_deposits:
            problems.append(f"core {core.seat} has {len(home)} home deposits")
    if len(state.deposits) != 2 * (rules.home_deposits + rules.field_deposits):
        problems.append(f"{len(state.deposits)} deposits")
    if any(d.amount % 10 or not 150 <= d.amount <= 300 for d in state.deposits):
        problems.append("deposit amount out of range")
    return problems


@pytest.mark.parametrize("seed", SEEDS)
def test_generated_maps_follow_the_rules(seed):
    assert check_map(new_game(RULES, seed)) == []


def test_start_position():
    state = new_game(RULES, 7)
    assert state.turn == 0
    assert state.banks == (100, 100)
    assert [(u.seat, u.id, u.kind) for u in state.units] == [
        (0, 1, Kind.WORKER),
        (0, 2, Kind.WORKER),
        (1, 1, Kind.WORKER),
        (1, 2, Kind.WORKER),
    ]
    core = state.cores[0].pos
    assert [u.pos for u in state.units[:2]] == [Pos(core.x + 1, core.y), Pos(core.x, core.y + 1)]


def test_the_seed_decides_the_map():
    assert state_hash(new_game(RULES, 3)) == state_hash(new_game(RULES, 3))
    assert len({state_hash(new_game(RULES, s)) for s in range(20)}) == 20


def test_maps_need_room():
    with pytest.raises(ValueError, match="16 x 16"):
        new_game(Rules(width=12, height=12), 1)
