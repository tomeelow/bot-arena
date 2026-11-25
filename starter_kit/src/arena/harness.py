"""The bot side of a match.

`BotSession` runs one bot through one match, one protocol message at a time, whatever
carries the messages: `main` reads them from stdin (local and ranked matches), and the
browser will hand them over from a Web Worker (Phase 8).

    python -m arena.harness my_bot.py
    python -m arena.harness builtin:rush
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from random import Random
from typing import Any

from arena_engine import Attack, Mine, Move, Spawn, Unload, order_to_plain

from .bot import Bot
from .builtin import builtin_factory
from .protocol import (
    decode_event,
    decode_map_info,
    decode_observation,
    decode_rules,
    encode,
    truncate,
)

ORDER_TYPES = (Move, Mine, Attack, Unload, Spawn)


def load_bot(spec: str) -> Callable[[], Bot]:
    """What makes the bot named by `spec`: a path to a .py file, `builtin:NAME`, or
    `builtin:NAME~EPS` for a built-in that swaps in a random order with probability EPS."""
    if spec.startswith("builtin:"):
        return builtin_factory(spec.removeprefix("builtin:"))
    return _load_file(Path(spec))


def _load_file(path: Path) -> type[Bot]:
    module_spec = importlib.util.spec_from_file_location("bot_main", path)
    if module_spec is None or module_spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    found = [
        v
        for v in vars(module).values()
        if isinstance(v, type) and issubclass(v, Bot) and v.__module__ == module.__name__
    ]
    if len(found) != 1:
        raise TypeError(f"{path} must define exactly one Bot subclass, found {len(found)}")
    return found[0]


class BotSession:
    def __init__(self, make_bot: Callable[[], Bot]) -> None:
        self.make_bot = make_bot
        self.bot: Bot | None = None
        self.log_limit = 0

    def handle(self, message: dict[str, Any]) -> dict[str, Any]:
        match message["t"]:
            case "init":
                return self._init(message)
            case "turn":
                return self._turn(message)
            case other:
                raise ValueError(f"unknown message type {other!r}")

    def _init(self, message: dict[str, Any]) -> dict[str, Any]:
        self.log_limit = message["limits"]["log_max_bytes_per_turn"]
        bot = self.make_bot()
        bot.map = decode_map_info(message["map"])
        bot.rules = decode_rules(message["rules"])
        bot.rng = Random(message["rng_seed"])
        _, log = self._capture(bot.setup)
        self.bot = bot
        return {"t": "ready", "log": log}

    def _turn(self, message: dict[str, Any]) -> dict[str, Any]:
        bot = self.bot
        if bot is None:
            raise RuntimeError("turn received before init")
        bot.events = tuple(decode_event(e) for e in message["events"])
        obs = decode_observation(message["obs"])
        orders, log = self._capture(lambda: bot.act(obs))
        if not isinstance(orders, list) or not all(isinstance(o, ORDER_TYPES) for o in orders):
            raise TypeError("act() must return a list of Move, Mine, Attack, Unload or Spawn")
        return {
            "t": "orders",
            "n": message["n"],
            "orders": [order_to_plain(o) for o in orders],
            "log": log,
        }

    def _capture[T](self, fn: Callable[[], T]) -> tuple[T, str]:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            value = fn()
        return value, truncate(buffer.getvalue(), self.log_limit)


def main() -> None:
    protocol = os.fdopen(os.dup(1), "wb", buffering=0)
    os.dup2(2, 1)  # whatever else writes to fd 1 now lands on stderr, never in the protocol
    sys.stdout = sys.stderr
    session = BotSession(load_bot(sys.argv[1]))
    for line in sys.stdin.buffer:
        protocol.write(encode(session.handle(json.loads(line))))


if __name__ == "__main__":
    main()
