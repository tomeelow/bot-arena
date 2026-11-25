"""Test helpers: hand-drawn scenarios, a seeded random bot, and seat swapping."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from random import Random

from arena_engine import (
    UNIT_STATS,
    Attack,
    Core,
    Deposit,
    Dir,
    Event,
    GameState,
    Kind,
    MapInfo,
    Mine,
    Move,
    Observation,
    Order,
    Pos,
    Rules,
    Spawn,
    Unit,
    Unload,
    map_info,
    new_game,
    observe,
    step,
)
from arena_engine.geometry import DIRS, adjacent, dir_to_frame, dist2, mirror, step_pos

UNIT_LETTERS = {"w": Kind.WORKER, "s": Kind.SOLDIER, "x": Kind.SCOUT}


def scenario(
    *rows: str,
    hp: dict[tuple[int, int], int] | None = None,
    cargo: dict[tuple[int, int], int] | None = None,
    amounts: dict[Pos, int] | None = None,
    banks: tuple[int, int] = (0, 0),
    **rule_overrides: int,
) -> GameState:
    """A state drawn as text. `#` wall, `$` deposit (100 unless in `amounts`), `C`/`c` Cores,
    `W`/`S`/`X` seat-0 worker/soldier/scout and `w`/`s`/`x` seat 1's. Ids follow reading order.
    """
    rules = Rules(width=len(rows[0]), height=len(rows), **rule_overrides)
    walls: set[Pos] = set()
    deposits: list[Deposit] = []
    cores: dict[int, Core] = {}
    units: list[Unit] = []
    next_id = [1, 1]
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            p = Pos(x, y)
            if ch == "#":
                walls.add(p)
            elif ch == "$":
                deposits.append(Deposit(p, (amounts or {}).get(p, 100)))
            elif ch in "Cc":
                seat = 0 if ch == "C" else 1
                cores[seat] = Core(seat, p, rules.core_hp)
            elif ch.lower() in UNIT_LETTERS:
                seat = 0 if ch.isupper() else 1
                kind = UNIT_LETTERS[ch.lower()]
                uid = next_id[seat]
                next_id[seat] += 1
                units.append(
                    Unit(
                        seat,
                        uid,
                        kind,
                        p,
                        (hp or {}).get((seat, uid), UNIT_STATS[kind].hp),
                        (cargo or {}).get((seat, uid), 0),
                    )
                )
            elif ch != ".":
                raise ValueError(f"unknown map character {ch!r}")
    return GameState(
        rules=rules,
        turn=0,
        walls=frozenset(walls),
        deposits=tuple(sorted(deposits, key=lambda d: d.pos)),
        cores=(cores[0], cores[1]),
        units=tuple(sorted(units, key=lambda u: (u.seat, u.id))),
        banks=banks,
        next_id=(next_id[0], next_id[1]),
        spent=(0, 0),
        lost=0,
    )


def unit(state: GameState, seat: int, uid: int) -> Unit | None:
    return next((u for u in state.units if u.seat == seat and u.id == uid), None)


def alive(state: GameState, seat: int, uid: int) -> Unit:
    found = unit(state, seat, uid)
    assert found is not None, f"seat {seat} unit {uid} is not on the board"
    return found


def rel(seat: int, absolute: Dir) -> Dir:
    """The direction `seat` must send to move in the absolute direction given."""
    return dir_to_frame(absolute, seat)


type Bot = Callable[[Observation, MapInfo, tuple[Event, ...]], list[Order]]


@dataclass
class RandomBot:
    """Seeded, mostly sensible random play that only looks at its own observation, so the
    same bot plays the mirror-image game from either seat."""

    seed: int

    def __post_init__(self) -> None:
        self.rng = Random(self.seed)

    def __call__(self, obs: Observation, info: MapInfo, events: tuple[Event, ...]) -> list[Order]:
        rng = self.rng
        sites = set(info.deposit_sites)
        enemies = {e.pos for e in obs.enemies} | {info.enemy_core}
        orders: list[Order] = []
        for u in obs.units:
            near = [d for d in DIRS if step_pos(u.pos, d) in enemies]
            mineable = [d for d in DIRS if step_pos(u.pos, d) in sites]
            roll = rng.randrange(100)
            if u.kind is Kind.SOLDIER and near and roll < 90:
                orders.append(Attack(u.id, rng.choice(near)))
            elif u.kind is Kind.WORKER and u.cargo > 0 and adjacent(u.pos, info.my_core):
                orders.append(Unload(u.id))
            elif u.kind is Kind.WORKER and mineable and u.cargo < 10 and roll < 80:
                orders.append(Mine(u.id, rng.choice(mineable)))
            elif u.kind is Kind.WORKER and u.cargo >= 6 and roll < 70:
                orders.append(Move(u.id, _toward(u.pos, info.my_core, rng)))
            elif u.kind is Kind.WORKER and u.cargo < 6 and roll < 50:
                target = min(info.deposit_sites, key=lambda p: dist2(p, u.pos))
                orders.append(Move(u.id, _toward(u.pos, target, rng)))
            elif u.kind is Kind.SOLDIER and roll < 60:
                orders.append(Move(u.id, _toward(u.pos, info.enemy_core, rng)))
            elif roll < 85:
                orders.append(Move(u.id, rng.choice(DIRS)))
        if rng.randrange(100) < 30:
            orders.append(Spawn(rng.choice(list(Kind)), rng.choice(DIRS)))
        return orders


def _toward(src: Pos, dst: Pos, rng: Random) -> Dir:
    best = min(dist2(step_pos(src, d), dst) for d in DIRS)
    return rng.choice([d for d in DIRS if dist2(step_pos(src, d), dst) == best])


@dataclass(frozen=True)
class Game:
    states: list[GameState]
    events: list[tuple[tuple[Event, ...], tuple[Event, ...]]]  # events produced by each step
    orders: list[tuple[list[Order], list[Order]]]


def play(bots: tuple[Bot, Bot], seed: int, turns: int, rules: Rules | None = None) -> Game:
    state = new_game(rules or Rules(), seed)
    infos = (map_info(state, 0), map_info(state, 1))
    game = Game([state], [], [])
    last: tuple[tuple[Event, ...], tuple[Event, ...]] = ((), ())
    while state.outcome is None and state.turn < turns:
        orders = (
            bots[0](observe(state, 0), infos[0], last[0]),
            bots[1](observe(state, 1), infos[1], last[1]),
        )
        result = step(state, {0: orders[0], 1: orders[1]})
        state, last = result.state, result.events
        game.states.append(state)
        game.events.append(last)
        game.orders.append(orders)
    return game


def swap_seats(state: GameState) -> GameState:
    """The same position with the seats exchanged: rotate the board, relabel the players."""
    rules = state.rules

    def flip[T](pair: tuple[T, T]) -> tuple[T, T]:
        return (pair[1], pair[0])

    units = [replace(u, seat=1 - u.seat, pos=mirror(u.pos, rules)) for u in state.units]
    cores = [replace(c, seat=1 - c.seat, pos=mirror(c.pos, rules)) for c in state.cores]
    deposits = [replace(d, pos=mirror(d.pos, rules)) for d in state.deposits]
    return replace(
        state,
        walls=frozenset(mirror(p, rules) for p in state.walls),
        deposits=tuple(sorted(deposits, key=lambda d: d.pos)),
        cores=(cores[1], cores[0]),
        units=tuple(sorted(units, key=lambda u: (u.seat, u.id))),
        banks=flip(state.banks),
        next_id=flip(state.next_id),
        spent=flip(state.spent),
        outcome=state.outcome.mirrored() if state.outcome else None,
    )


def crystal_total(state: GameState) -> int:
    return (
        sum(d.amount for d in state.deposits)
        + sum(u.cargo for u in state.units)
        + sum(state.banks)
        + sum(state.spent)
        + state.lost
    )
