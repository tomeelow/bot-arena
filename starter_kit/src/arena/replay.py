"""Replay format v1 (ADR-007): seed, rules, engine version and every order.

A replay needs no bot code to play back. Loading one re-simulates it and checks the final
state hash, so a replay that doesn't reproduce is rejected rather than shown wrong.
"""

import gzip
import hashlib
import inspect
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from arena_engine import (
    ENGINE_VERSION,
    GameState,
    Rules,
    new_game,
    order_to_plain,
    parse_order,
    state_hash,
    step,
    to_plain,
)

from .builtin import BUILTINS
from .runner import MatchRecord

FORMAT = 1


class ReplayError(ValueError):
    pass


def to_dict(record: MatchRecord) -> dict[str, Any]:
    assert record.final_state is not None
    return {
        "format": FORMAT,
        "engine_version": ENGINE_VERSION,
        "seed": record.seed,
        "rules": to_plain(record.rules),
        "players": [
            {"seat": seat, "bot": spec, "code_sha256": code_hash(spec)}
            for seat, spec in enumerate(record.players)
        ],
        "turns": [
            {"orders": [[order_to_plain(o) for o in side] for side in orders], "ms": list(ms)}
            for orders, ms in zip(record.orders, record.think_ms, strict=True)
        ],
        "result": asdict(record.result),
        "final_hash": state_hash(record.final_state),
    }


def encode(record: MatchRecord) -> bytes:
    return gzip.compress(json.dumps(to_dict(record)).encode(), mtime=0)


def save(record: MatchRecord, path: Path) -> None:
    path.write_bytes(encode(record))


def save_logs(record: MatchRecord, path: Path) -> None:
    """Bot logs, kept apart from the replay: they belong to each bot's owner."""
    logs = {f"seat{seat}": record.logs[seat] for seat in (0, 1)}
    path.write_text(json.dumps(logs, indent=1))


@dataclass(frozen=True)
class Replay:
    data: dict[str, Any]
    states: list[GameState]


def load(path: Path) -> Replay:
    return decode(path.read_bytes())


def decode(raw: bytes) -> Replay:
    """A replay from its bytes, re-simulated and checked against its final hash."""
    data = json.loads(gzip.decompress(raw))
    if data.get("format") != FORMAT:
        raise ReplayError(f"unsupported replay format {data.get('format')!r}")
    if data["engine_version"] != ENGINE_VERSION:
        raise ReplayError(
            f"recorded with engine {data['engine_version']}; this is engine {ENGINE_VERSION}"
        )
    state = new_game(Rules(**data["rules"]), data["seed"])
    states = [state]
    for turn in data["turns"]:
        orders = {seat: [parse_order(o) for o in turn["orders"][seat]] for seat in (0, 1)}
        state = step(state, orders).state
        states.append(state)
    if state_hash(state) != data["final_hash"]:
        raise ReplayError("re-simulating the orders does not reproduce the recorded final state")
    return Replay(data, states)


def code_hash(spec: str) -> str:
    if spec.startswith("builtin:"):
        cls = BUILTINS[spec.removeprefix("builtin:").partition("~")[0]]
        source = Path(inspect.getfile(cls)).read_bytes()
    else:
        source = Path(spec).read_bytes()
    return "sha256:" + hashlib.sha256(source).hexdigest()
