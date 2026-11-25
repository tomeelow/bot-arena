"""The observation rule (GAME_RULES.md §6): a seat sees its visible cells and nothing else.

Two states that differ only in what a seat cannot see must give that seat identical
observations. Any new Observation field needs coverage here.
"""

from dataclasses import fields, replace

from engine_support import RandomBot, play
from hypothesis import given, settings
from hypothesis import strategies as st

from arena_engine import (
    UNIT_STATS,
    GameState,
    Kind,
    Observation,
    Pos,
    SeenUnit,
    Unit,
    observe,
    visible_cells,
)

positions = st.integers(min_value=0, max_value=2**32)


@st.composite
def midgame(draw: st.DrawFn) -> tuple[GameState, int]:
    seed = draw(positions)
    turns = draw(st.integers(min_value=0, max_value=200))
    game = play((RandomBot(seed), RandomBot(seed + 1)), seed, turns)
    return game.states[-1], draw(st.integers(min_value=0, max_value=1))


def free_cells(state: GameState) -> list[Pos]:
    taken = (
        set(state.walls)
        | {d.pos for d in state.deposits}
        | {c.pos for c in state.cores}
        | {u.pos for u in state.units}
    )
    return [
        p
        for y in range(state.rules.height)
        for x in range(state.rules.width)
        if (p := Pos(x, y)) not in taken
    ]


def hidden_free_cells(state: GameState, seat: int) -> list[Pos]:
    seen = visible_cells(state, seat)
    return [p for p in free_cells(state) if p not in seen]


@st.composite
def hidden_change(draw: st.DrawFn, state: GameState, seat: int) -> GameState:
    """Change some things `seat` cannot see: hidden enemy units, all enemy cargo and
    counters, hidden deposits, and the enemy Core while it is out of sight."""
    enemy = 1 - seat
    seen = visible_cells(state, seat)
    free = hidden_free_cells(state, seat)
    units: list[Unit] = []
    for u in state.units:
        if u.seat != enemy:
            units.append(u)
            continue
        cargo = draw(st.integers(0, 10)) if u.kind is Kind.WORKER else 0
        if u.pos in seen:
            units.append(replace(u, cargo=cargo))
        elif draw(st.booleans()):
            hp = draw(st.integers(1, UNIT_STATS[u.kind].hp))
            pos = draw(st.sampled_from(free)) if free and draw(st.booleans()) else u.pos
            if pos not in {v.pos for v in units}:
                units.append(replace(u, hp=hp, pos=pos, cargo=cargo))
    spare = [p for p in free if p not in {u.pos for u in units}]
    if spare and draw(st.booleans()):
        kind = draw(st.sampled_from(list(Kind)))
        units.append(Unit(enemy, 900, kind, draw(st.sampled_from(spare)), UNIT_STATS[kind].hp))

    deposits = tuple(
        d if d.pos in seen else replace(d, amount=draw(st.integers(0, 300))) for d in state.deposits
    )
    cores = list(state.cores)
    if cores[enemy].pos not in seen:
        cores[enemy] = replace(cores[enemy], hp=draw(st.integers(1, 400)))

    def bump(pair: tuple[int, int]) -> tuple[int, int]:
        values = list(pair)
        values[enemy] = draw(st.integers(0, 10_000))
        return (values[0], values[1])

    return replace(
        state,
        units=tuple(sorted(units, key=lambda u: (u.seat, u.id))),
        deposits=deposits,
        cores=(cores[0], cores[1]),
        banks=bump(state.banks),
        spent=bump(state.spent),
        next_id=bump(state.next_id),
        lost=draw(st.integers(0, 1000)),
    )


@settings(max_examples=60, deadline=None)
@given(st.data())
def test_changes_out_of_sight_do_not_change_the_observation(data):
    state, seat = data.draw(midgame())
    changed = data.draw(hidden_change(state, seat))
    assert observe(changed, seat) == observe(state, seat)


@settings(max_examples=20, deadline=None)
@given(st.data())
def test_changes_in_sight_do_change_the_observation(data):
    """The control: proves the test above could catch a leak. An enemy is placed in sight
    rather than waited for, because random games often have none."""
    state, seat = data.draw(midgame())
    seen = visible_cells(state, seat)
    spots = [p for p in free_cells(state) if p in seen]
    assert spots, "a seat always sees free cells around its own Core"
    kind = data.draw(st.sampled_from(list(Kind)))
    intruder = Unit(1 - seat, 900, kind, data.draw(st.sampled_from(spots)), UNIT_STATS[kind].hp)

    def with_units(*extra: Unit) -> GameState:
        units = sorted([*state.units, *extra], key=lambda u: (u.seat, u.id))
        return replace(state, units=tuple(units))

    arrived = with_units(intruder)
    hurt = with_units(replace(intruder, hp=intruder.hp - 1))
    assert observe(arrived, seat) != observe(state, seat)
    assert observe(hurt, seat) != observe(arrived, seat)


def test_observation_fields_are_the_reviewed_set():
    """Adding a field means adding fog coverage above, then updating this list."""
    assert [f.name for f in fields(Observation)] == [
        "turn",
        "bank",
        "core_hp",
        "units",
        "enemies",
        "enemy_core_hp",
        "deposits",
    ]
    assert [f.name for f in fields(SeenUnit)] == ["kind", "pos", "hp"]  # no id, no cargo
