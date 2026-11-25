"""The Bot Arena bot API. A bot is a subclass of `Bot` whose `act` returns a list of orders.

Everything a bot needs is importable from here: the order types, what an observation holds,
grid geometry and a pathfinding helper. The rules: docs/GAME_RULES.md.
"""

from arena_engine import (
    UNIT_STATS,
    Attack,
    Deposit,
    Dir,
    Event,
    InvalidOrder,
    Kind,
    MapInfo,
    Mine,
    Move,
    Observation,
    Order,
    OwnUnit,
    Pos,
    Rules,
    SeenUnit,
    Spawn,
    SpawnBlocked,
    UnitLost,
    Unload,
)
from arena_engine.geometry import DIRS, adjacent, dist2, step_pos

from .bot import Bot
from .grid import Grid

__all__ = [
    "DIRS",
    "UNIT_STATS",
    "Attack",
    "Bot",
    "Deposit",
    "Dir",
    "Event",
    "Grid",
    "InvalidOrder",
    "Kind",
    "MapInfo",
    "Mine",
    "Move",
    "Observation",
    "Order",
    "OwnUnit",
    "Pos",
    "Rules",
    "SeenUnit",
    "Spawn",
    "SpawnBlocked",
    "UnitLost",
    "Unload",
    "adjacent",
    "dist2",
    "step_pos",
]
