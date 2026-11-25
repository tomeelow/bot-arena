"""What each seat may see (GAME_RULES.md §6). Every observation field needs a fog test."""

from math import isqrt

from .geometry import in_bounds, to_frame
from .model import (
    UNIT_STATS,
    Deposit,
    GameState,
    MapInfo,
    Observation,
    OwnUnit,
    Pos,
    SeenUnit,
)


def visible_cells(state: GameState, seat: int) -> frozenset[Pos]:
    """Absolute cells within vision of `seat`'s living units and Core."""
    core = state.cores[seat]
    viewers = [(core.pos, state.rules.core_vision)] if core.hp > 0 else []
    viewers += [(u.pos, UNIT_STATS[u.kind].vision) for u in state.units if u.seat == seat]
    cells: set[Pos] = set()
    for center, r2 in viewers:
        reach = isqrt(r2)
        for dy in range(-reach, reach + 1):
            for dx in range(-reach, reach + 1):
                p = Pos(center.x + dx, center.y + dy)
                if dx * dx + dy * dy <= r2 and in_bounds(p, state.rules):
                    cells.add(p)
    return frozenset(cells)


def observe(state: GameState, seat: int) -> Observation:
    """`seat`'s fogged view of `state`, in its own frame."""
    rules = state.rules
    seen = visible_cells(state, seat)
    enemy_core = state.cores[1 - seat]

    def rel(p: Pos) -> Pos:
        return to_frame(p, seat, rules)

    units = tuple(
        OwnUnit(u.id, u.kind, rel(u.pos), u.hp, u.cargo) for u in state.units if u.seat == seat
    )
    enemies = sorted(
        (
            SeenUnit(u.kind, rel(u.pos), u.hp)
            for u in state.units
            if u.seat != seat and u.pos in seen
        ),
        key=lambda e: e.pos,
    )
    deposits = sorted(
        (Deposit(rel(d.pos), d.amount) for d in state.deposits if d.pos in seen),
        key=lambda d: d.pos,
    )
    return Observation(
        turn=state.turn,
        bank=state.banks[seat],
        core_hp=state.cores[seat].hp,
        units=units,
        enemies=tuple(enemies),
        enemy_core_hp=enemy_core.hp if enemy_core.pos in seen else None,
        deposits=tuple(deposits),
    )


def map_info(state: GameState, seat: int) -> MapInfo:
    """The public, static part of the map, in `seat`'s frame. Safe to call on any turn."""
    rules = state.rules
    return MapInfo(
        width=rules.width,
        height=rules.height,
        max_turns=rules.max_turns,
        walls=tuple(sorted(to_frame(p, seat, rules) for p in state.walls)),
        deposit_sites=tuple(sorted(to_frame(d.pos, seat, rules) for d in state.deposits)),
        my_core=to_frame(state.cores[seat].pos, seat, rules),
        enemy_core=to_frame(state.cores[1 - seat].pos, seat, rules),
    )
