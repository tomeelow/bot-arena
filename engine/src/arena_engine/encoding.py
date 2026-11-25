"""Canonical encodings: the state hash and the order schema.

`parse_order` reads untrusted input (a bot's reply), so it accepts exactly the documented
shapes and nothing else.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import fields, is_dataclass
from enum import StrEnum
from typing import cast

from .model import Attack, Dir, GameState, Kind, Mine, Move, Order, Spawn, Unload

type Plain = bool | int | str | list[Plain] | dict[str, Plain] | None

MAX_UNIT_ID = 1_000_000
ORDER_FIELDS: dict[str, set[str]] = {
    "move": {"type", "unit", "dir"},
    "mine": {"type", "unit", "dir"},
    "attack": {"type", "unit", "dir"},
    "unload": {"type", "unit"},
    "spawn": {"type", "kind", "dir"},
}
DIRECTED: dict[str, Callable[[int, Dir], Order]] = {"move": Move, "mine": Mine, "attack": Attack}


class OrderFormatError(ValueError):
    pass


def canonical_json(value: Plain) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def to_plain(value: object) -> Plain:
    """Dataclasses, tuples, sets and enums as JSON-ready data. Sets come out sorted."""
    if value is None or isinstance(value, bool | int):
        return value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, str):
        return value
    if isinstance(value, float):
        raise TypeError("floats are not allowed in game data")
    if isinstance(value, frozenset | set):
        items = [to_plain(v) for v in cast(frozenset[object], value)]
        return sorted(items, key=canonical_json)
    if isinstance(value, tuple | list):
        return [to_plain(v) for v in cast(tuple[object, ...], value)]
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_plain(getattr(value, f.name)) for f in fields(value)}
    raise TypeError(f"cannot encode {type(value).__name__}")


def state_hash(state: GameState) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(to_plain(state)).encode()).hexdigest()


def order_to_plain(order: Order) -> dict[str, Plain]:
    match order:
        case Move(unit, d) | Mine(unit, d) | Attack(unit, d):
            name = {Move: "move", Mine: "mine", Attack: "attack"}[type(order)]
            return {"type": name, "unit": unit, "dir": d.value}
        case Unload(unit):
            return {"type": "unload", "unit": unit}
        case Spawn(kind, d):
            return {"type": "spawn", "kind": kind.value, "dir": d.value}


def parse_order(data: object) -> Order:
    if not isinstance(data, dict):
        raise OrderFormatError("an order must be an object")
    obj = cast(dict[object, object], data)
    name = obj.get("type")
    if not isinstance(name, str) or name not in ORDER_FIELDS:
        raise OrderFormatError(f"unknown order type: {name!r}")
    if set(obj) != ORDER_FIELDS[name]:
        raise OrderFormatError(f"{name} needs exactly the fields {sorted(ORDER_FIELDS[name])}")
    if name == "spawn":
        return Spawn(_enum(Kind, obj["kind"]), _enum(Dir, obj["dir"]))
    unit = _unit_id(obj["unit"])
    if name == "unload":
        return Unload(unit)
    return DIRECTED[name](unit, _enum(Dir, obj["dir"]))


def _unit_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= MAX_UNIT_ID:
        raise OrderFormatError(f"unit must be an id between 1 and {MAX_UNIT_ID}")
    return value


def _enum[E: StrEnum](enum: type[E], value: object) -> E:
    allowed = [m.value for m in enum]
    if not isinstance(value, str) or value not in allowed:
        raise OrderFormatError(f"{enum.__name__.lower()} must be one of {allowed}")
    return enum(value)
