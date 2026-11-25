"""Deterministic Bot Arena game engine: rules, fog of war, turn resolution.

The whole public surface is re-exported here. Rules: docs/GAME_RULES.md.
"""

from .encoding import OrderFormatError, order_to_plain, parse_order, state_hash, to_plain
from .fog import map_info, observe, visible_cells
from .mapgen import new_game
from .model import (
    UNIT_STATS,
    Attack,
    Core,
    Deposit,
    Dir,
    EndReason,
    Event,
    GameState,
    InvalidOrder,
    Kind,
    MapInfo,
    Mine,
    Move,
    Observation,
    Order,
    Outcome,
    OwnUnit,
    Pos,
    Rules,
    SeenUnit,
    Spawn,
    SpawnBlocked,
    StepResult,
    Unit,
    UnitLost,
    UnitStats,
    Unload,
)
from .rules import score, step

ENGINE_VERSION = "0.1.0"


def outcome(state: GameState) -> Outcome | None:
    """None while the game is running."""
    return state.outcome


__all__ = [
    "ENGINE_VERSION",
    "UNIT_STATS",
    "Attack",
    "Core",
    "Deposit",
    "Dir",
    "EndReason",
    "Event",
    "GameState",
    "InvalidOrder",
    "Kind",
    "MapInfo",
    "Mine",
    "Move",
    "Observation",
    "Order",
    "OrderFormatError",
    "Outcome",
    "OwnUnit",
    "Pos",
    "Rules",
    "SeenUnit",
    "Spawn",
    "SpawnBlocked",
    "StepResult",
    "Unit",
    "UnitLost",
    "UnitStats",
    "Unload",
    "map_info",
    "new_game",
    "observe",
    "order_to_plain",
    "outcome",
    "parse_order",
    "score",
    "state_hash",
    "step",
    "to_plain",
    "visible_cells",
]
