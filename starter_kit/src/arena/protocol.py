"""The bot protocol: one JSON object per line between the host and the bot's harness.

    host -> bot   {"t": "init", "map": ..., "rules": ..., "limits": ..., "rng_seed": ...}
    bot  -> host  {"t": "ready", "log": "..."}
    host -> bot   {"t": "turn", "n": 17, "obs": ..., "events": [...]}
    bot  -> host  {"t": "orders", "n": 17, "orders": [...], "log": "..."}

Observations, orders and events use the engine's canonical encodings. The host treats every
reply as hostile (`parse_ready`, `parse_orders`); the bot trusts the host, so its decoders
are plain.
"""

import json
from dataclasses import asdict
from typing import Any

from arena_engine import (
    Deposit,
    Event,
    GameState,
    InvalidOrder,
    Kind,
    MapInfo,
    Observation,
    Order,
    OrderFormatError,
    OwnUnit,
    Pos,
    Rules,
    SeenUnit,
    SpawnBlocked,
    UnitLost,
    event_to_plain,
    map_info,
    observe,
    parse_order,
    to_plain,
)

from .limits import Limits

TRUNCATED = "...[truncated]"


class ProtocolError(ValueError):
    """A reply that breaks the protocol. The bot loses with `invalid_output`."""


def encode(message: dict[str, Any]) -> bytes:
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def truncate(text: str, max_bytes: int) -> str:
    raw = text.encode()
    if len(raw) <= max_bytes:
        return text
    return raw[: max_bytes - len(TRUNCATED)].decode(errors="ignore") + TRUNCATED


# --- host side ---------------------------------------------------------------------------


def init_message(state: GameState, seat: int, limits: Limits, rng_seed: int) -> dict[str, Any]:
    return {
        "t": "init",
        "map": to_plain(map_info(state, seat)),
        "rules": to_plain(state.rules),
        "limits": asdict(limits),
        "rng_seed": rng_seed,
    }


def turn_message(state: GameState, seat: int, events: tuple[Event, ...]) -> dict[str, Any]:
    return {
        "t": "turn",
        "n": state.turn,
        "obs": to_plain(observe(state, seat)),
        "events": [event_to_plain(e) for e in events],
    }


def parse_ready(line: bytes, limits: Limits) -> str:
    data = _load(line, limits)
    if set(data) != {"t", "log"} or data["t"] != "ready":
        raise ProtocolError('expected {"t": "ready", "log": ...}')
    return _log(data["log"], limits)


def parse_orders(line: bytes, turn: int, limits: Limits) -> tuple[list[Order], str]:
    data = _load(line, limits)
    if set(data) != {"t", "n", "orders", "log"} or data["t"] != "orders":
        raise ProtocolError('expected {"t": "orders", "n": ..., "orders": [...], "log": ...}')
    n = data["n"]
    if type(n) is not int or n != turn:
        raise ProtocolError(f"reply is for turn {n!r}, expected {turn}")
    raw = data["orders"]
    if not isinstance(raw, list):
        raise ProtocolError("orders must be a list")
    if len(raw) > limits.max_orders:
        raise ProtocolError(f"more than {limits.max_orders} orders")
    try:
        orders = [parse_order(o) for o in raw]
    except OrderFormatError as e:
        raise ProtocolError(f"bad order: {e}") from e
    return orders, _log(data["log"], limits)


def _load(line: bytes, limits: Limits) -> dict[str, Any]:
    if len(line) > limits.reply_max_bytes:
        raise ProtocolError(f"reply longer than {limits.reply_max_bytes} bytes")
    try:
        data = json.loads(line, parse_constant=_reject_constant)
    except (ValueError, RecursionError) as e:
        raise ProtocolError("reply is not valid JSON") from e
    if not isinstance(data, dict):
        raise ProtocolError("reply must be a JSON object")
    return data


def _reject_constant(name: str) -> None:
    raise ValueError(f"{name} is not allowed")


def _log(value: object, limits: Limits) -> str:
    if not isinstance(value, str):
        raise ProtocolError("log must be a string")
    return truncate(value, limits.log_max_bytes_per_turn)


# --- bot side ----------------------------------------------------------------------------


def decode_map_info(d: dict[str, Any]) -> MapInfo:
    return MapInfo(
        width=d["width"],
        height=d["height"],
        max_turns=d["max_turns"],
        walls=tuple(_pos(p) for p in d["walls"]),
        deposit_sites=tuple(_pos(p) for p in d["deposit_sites"]),
        my_core=_pos(d["my_core"]),
        enemy_core=_pos(d["enemy_core"]),
    )


def decode_rules(d: dict[str, Any]) -> Rules:
    return Rules(**d)


def decode_observation(d: dict[str, Any]) -> Observation:
    return Observation(
        turn=d["turn"],
        bank=d["bank"],
        core_hp=d["core_hp"],
        units=tuple(
            OwnUnit(u["id"], Kind(u["kind"]), _pos(u["pos"]), u["hp"], u["cargo"])
            for u in d["units"]
        ),
        enemies=tuple(SeenUnit(Kind(e["kind"]), _pos(e["pos"]), e["hp"]) for e in d["enemies"]),
        enemy_core_hp=d["enemy_core_hp"],
        deposits=tuple(Deposit(_pos(x["pos"]), x["amount"]) for x in d["deposits"]),
    )


def decode_event(d: dict[str, Any]) -> Event:
    match d["type"]:
        case "invalid_order":
            return InvalidOrder(parse_order(d["order"]), d["reason"])
        case "spawn_blocked":
            return SpawnBlocked(Kind(d["kind"]), _pos(d["pos"]))
        case "unit_lost":
            return UnitLost(d["unit"], _pos(d["pos"]))
        case other:
            raise ValueError(f"unknown event type {other!r}")


def _pos(v: list[int]) -> Pos:
    return Pos(v[0], v[1])
