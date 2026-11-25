"""Game data: positions, units, orders, state and observations. Everything is immutable."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple


class Pos(NamedTuple):
    x: int
    y: int


class Dir(StrEnum):
    N = "N"
    E = "E"
    S = "S"
    W = "W"


class Kind(StrEnum):
    WORKER = "worker"
    SOLDIER = "soldier"
    SCOUT = "scout"


class EndReason(StrEnum):
    CORE_DESTROYED = "core_destroyed"
    TURN_LIMIT = "turn_limit"


@dataclass(frozen=True, slots=True)
class UnitStats:
    cost: int
    hp: int
    vision: int  # squared radius
    attack: int = 0
    carry: int = 0


UNIT_STATS: Mapping[Kind, UnitStats] = {
    Kind.WORKER: UnitStats(cost=50, hp=10, vision=8, carry=10),
    Kind.SOLDIER: UnitStats(cost=80, hp=30, vision=8, attack=5),
    Kind.SCOUT: UnitStats(cost=30, hp=5, vision=49),
}


@dataclass(frozen=True, slots=True)
class Rules:
    """Match parameters. The defaults are rules v1 (docs/GAME_RULES.md)."""

    width: int = 32
    height: int = 32
    max_turns: int = 400
    start_bank: int = 100
    core_hp: int = 400
    core_vision: int = 25
    mine_rate: int = 2
    max_units: int = 40
    wall_percent: int = 10
    core_clear_radius2: int = 4
    home_deposits: int = 2
    home_deposit_min_dist2: int = 9
    home_deposit_max_dist2: int = 25
    field_deposits: int = 5
    deposit_min: int = 150
    deposit_max: int = 300


@dataclass(frozen=True, slots=True)
class Unit:
    seat: int
    id: int
    kind: Kind
    pos: Pos
    hp: int
    cargo: int = 0


@dataclass(frozen=True, slots=True)
class Core:
    seat: int
    pos: Pos
    hp: int


@dataclass(frozen=True, slots=True)
class Deposit:
    pos: Pos
    amount: int


@dataclass(frozen=True, slots=True)
class Outcome:
    winner: int | None  # None is a draw
    reason: EndReason
    turns: int

    def mirrored(self) -> Outcome:
        winner = None if self.winner is None else 1 - self.winner
        return Outcome(winner, self.reason, self.turns)


@dataclass(frozen=True, slots=True)
class GameState:
    rules: Rules
    turn: int
    walls: frozenset[Pos]  # membership only: never iterate a set (see CLAUDE.md)
    deposits: tuple[Deposit, ...]  # sorted by pos
    cores: tuple[Core, Core]
    units: tuple[Unit, ...]  # sorted by (seat, id)
    banks: tuple[int, int]
    next_id: tuple[int, int]
    spent: tuple[int, int]  # crystals spent on spawns, kept for the conservation invariant
    lost: int  # crystals destroyed with Workers that died carrying them
    outcome: Outcome | None = None


# Orders, in the sender's seat-relative frame.


@dataclass(frozen=True, slots=True)
class Move:
    unit: int
    dir: Dir


@dataclass(frozen=True, slots=True)
class Mine:
    unit: int
    dir: Dir


@dataclass(frozen=True, slots=True)
class Attack:
    unit: int
    dir: Dir


@dataclass(frozen=True, slots=True)
class Unload:
    unit: int


@dataclass(frozen=True, slots=True)
class Spawn:
    kind: Kind
    dir: Dir


type Order = Move | Mine | Attack | Unload | Spawn
type UnitOrder = Move | Mine | Attack | Unload


# Private events, reported only to the seat they concern, in that seat's frame.


@dataclass(frozen=True, slots=True)
class InvalidOrder:
    order: Order
    reason: str


@dataclass(frozen=True, slots=True)
class SpawnBlocked:
    kind: Kind
    pos: Pos


@dataclass(frozen=True, slots=True)
class UnitLost:
    unit: int
    pos: Pos


type Event = InvalidOrder | SpawnBlocked | UnitLost


@dataclass(frozen=True, slots=True)
class StepResult:
    state: GameState
    events: tuple[tuple[Event, ...], tuple[Event, ...]]


# What a bot sees, in its seat-relative frame.


@dataclass(frozen=True, slots=True)
class OwnUnit:
    id: int
    kind: Kind
    pos: Pos
    hp: int
    cargo: int


@dataclass(frozen=True, slots=True)
class SeenUnit:
    kind: Kind
    pos: Pos
    hp: int


@dataclass(frozen=True, slots=True)
class Observation:
    turn: int
    bank: int
    core_hp: int
    units: tuple[OwnUnit, ...]  # sorted by id
    enemies: tuple[SeenUnit, ...]  # visible only, sorted by pos
    enemy_core_hp: int | None  # None unless the enemy Core is visible
    deposits: tuple[Deposit, ...]  # visible only, current amounts, sorted by pos


@dataclass(frozen=True, slots=True)
class MapInfo:
    """What is public from turn 0, in the seat's frame."""

    width: int
    height: int
    max_turns: int
    walls: tuple[Pos, ...]  # sorted
    deposit_sites: tuple[Pos, ...]  # sorted; amounts are fogged
    my_core: Pos
    enemy_core: Pos
