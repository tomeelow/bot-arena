"""The host side of a match: drives the engine and two bots over the protocol.

Your own bot runs as a subprocess; built-in bots run in-process through the same harness
and the same JSON messages. Locally, limits only produce warnings, except a generous
backstop that stops a hung bot. Ranked matches will run this loop with each bot in a jail
and the limits enforced (Phase 3).
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from arena_engine import Event, GameState, Order, Rules, new_game, step

from .bot import Bot
from .harness import BotSession, load_bot
from .limits import Limits
from .protocol import (
    ProtocolError,
    encode,
    init_message,
    parse_orders,
    parse_ready,
    turn_message,
)

STDERR_TAIL_BYTES = 8192
SEATS = (0, 1)


class Failure(StrEnum):
    TIMEOUT = "timeout"
    CRASH = "crash"
    MEMORY = "memory"
    INVALID_OUTPUT = "invalid_output"


@dataclass(frozen=True)
class Result:
    winner: int | None  # None is a draw
    reason: str  # an engine EndReason, a Failure, or "both_failed"
    turns: int
    detail: str = ""


@dataclass(frozen=True)
class Reply:
    line: bytes | None  # None: no usable reply (see `problem`)
    ms: float
    problem: Failure | None = None
    detail: str = ""


class Channel(Protocol):
    def send(self, message: dict[str, Any]) -> None: ...
    def receive(self, timeout_s: float) -> Reply: ...
    def close(self) -> str: ...  # whatever the bot wrote to stderr, for its owner


class InProcessChannel:
    """A trusted bot run in this process. The JSON round trip keeps it byte-for-byte on the
    same protocol as a subprocess."""

    def __init__(self, make_bot: Callable[[], Bot]) -> None:
        self.session = BotSession(make_bot)
        self.pending: bytes = b""
        self.error = ""

    def send(self, message: dict[str, Any]) -> None:
        self.pending = encode(message)

    def receive(self, timeout_s: float) -> Reply:
        start = time.perf_counter()
        try:
            reply = encode(self.session.handle(json.loads(self.pending)))
        except Exception:
            self.error = traceback.format_exc()
            return Reply(None, _ms_since(start), Failure.CRASH, "the bot raised an exception")
        return Reply(reply, _ms_since(start))

    def close(self) -> str:
        return self.error


class ProcessChannel:
    """A bot in its own process, talking JSON lines over stdin and stdout. `argv` starts the
    harness: directly for local play, or wrapped in a jail for ranked play."""

    def __init__(self, argv: list[str], max_line: int, env: dict[str, str] | None = None) -> None:
        self.proc = subprocess.Popen(
            argv,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.max_line = max_line
        self.replies: queue.Queue[tuple[float, bytes | None]] = queue.Queue()
        self.stderr: deque[bytes] = deque()
        self.sent_at = 0.0
        self.threads = [
            threading.Thread(target=self._read_stdout, daemon=True),
            threading.Thread(target=self._read_stderr, daemon=True),
        ]
        for t in self.threads:
            t.start()

    def send(self, message: dict[str, Any]) -> None:
        self.sent_at = time.perf_counter()
        try:
            assert self.proc.stdin is not None
            self.proc.stdin.write(encode(message))
            self.proc.stdin.flush()
        except BrokenPipeError, OSError:
            pass  # the bot is gone; receive() reports it

    def receive(self, timeout_s: float) -> Reply:
        remaining = timeout_s - (time.perf_counter() - self.sent_at)
        try:
            arrived, line = self.replies.get(timeout=max(0.0, remaining))
        except queue.Empty:
            ms = timeout_s * 1000
            return Reply(None, ms, Failure.TIMEOUT, f"no reply within {ms:.0f} ms")
        ms = (arrived - self.sent_at) * 1000
        if line is None:
            return Reply(None, ms, Failure.CRASH, "the bot process exited")
        if len(line) > self.max_line:
            return Reply(None, ms, Failure.INVALID_OUTPUT, "reply line too long")
        return Reply(line, ms)

    def close(self) -> str:
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        for t in self.threads:
            t.join(timeout=1)
        return b"".join(self.stderr).decode(errors="replace")

    def _read_stdout(self) -> None:
        assert self.proc.stdout is not None
        while line := self.proc.stdout.readline(self.max_line + 1):
            self.replies.put((time.perf_counter(), line))
            if not line.endswith(b"\n"):  # over-long: report it, then stop listening
                break
        self.replies.put((time.perf_counter(), None))

    def _read_stderr(self) -> None:
        assert self.proc.stderr is not None
        size = 0
        while chunk := os.read(self.proc.stderr.fileno(), 4096):
            self.stderr.append(chunk)
            size += len(chunk)
            while size > STDERR_TAIL_BYTES and len(self.stderr) > 1:
                size -= len(self.stderr.popleft())


type Opener = Callable[[str, Limits], Channel]


def open_channel(spec: str, limits: Limits) -> Channel:
    if spec.startswith("builtin:"):
        return InProcessChannel(load_bot(spec))
    return ProcessChannel([sys.executable, "-m", "arena.harness", spec], limits.reply_max_bytes)


@dataclass
class MatchRecord:
    seed: int
    rules: Rules
    players: tuple[str, str]
    orders: list[tuple[list[Order], list[Order]]] = field(default_factory=list)
    think_ms: list[tuple[int, int]] = field(default_factory=list)
    logs: tuple[list[tuple[int, str]], list[tuple[int, str]]] = ([], [])
    warnings: list[str] = field(default_factory=list)
    stderr: tuple[str, str] = ("", "")
    result: Result = Result(None, "", 0)
    final_state: GameState | None = None


def run_match(
    players: tuple[str, str],
    seed: int,
    rules: Rules | None = None,
    limits: Limits | None = None,
    *,
    opener: Opener = open_channel,
    enforce: bool = False,
) -> MatchRecord:
    """Play one match. `players` are bot specs: a .py path or `builtin:NAME`.

    By default limits only warn. With `enforce`, as in ranked play, a bot that overruns its
    setup budget or empties its time bank loses on time, and the wall-clock backstop is the
    ranked one."""
    rules = rules or Rules()
    limits = limits or Limits.load()
    turn_wait = (limits.turn_backstop_ms if enforce else limits.local_backstop_ms) / 1000
    init_wait = turn_wait + limits.init_ms / 1000 if enforce else turn_wait
    record = MatchRecord(seed, rules, players, logs=([], []))
    state = new_game(rules, seed)
    channels: list[Channel] = []
    budget = _Budget(limits)
    try:
        channels = [opener(p, limits) for p in players]
        inits = [init_message(state, seat, limits, rng_seed=2 * seed + seat) for seat in SEATS]
        lines, failures, ms = _exchange(channels, inits, init_wait)
        for seat in SEATS:
            if seat in failures:
                continue
            try:
                _note_log(record, seat, 0, parse_ready(lines[seat], limits), limits)
            except ProtocolError as e:
                failures[seat] = (Failure.INVALID_OUTPUT, str(e))
            if enforce and seat not in failures and ms[seat] > limits.init_ms:
                failures[seat] = (Failure.TIMEOUT, f"setup took {ms[seat]} ms of {limits.init_ms}")

        events: tuple[tuple[Event, ...], tuple[Event, ...]] = ((), ())
        while state.outcome is None and not failures:
            messages = [turn_message(state, seat, events[seat]) for seat in SEATS]
            lines, failures, ms = _exchange(channels, messages, turn_wait)
            orders: list[list[Order]] = [[], []]
            for seat in SEATS:
                if seat in failures:
                    continue
                try:
                    orders[seat], log = parse_orders(lines[seat], state.turn, limits)
                except ProtocolError as e:
                    failures[seat] = (Failure.INVALID_OUTPUT, str(e))
                    continue
                _note_log(record, seat, state.turn, log, limits)
            if failures:
                break
            budget.charge(state.turn, ms)
            if enforce:
                for seat in SEATS:
                    if budget.bank[seat] < 0:
                        failures[seat] = (Failure.TIMEOUT, f"time bank empty at turn {state.turn}")
                if failures:
                    break
            record.orders.append((orders[0], orders[1]))
            record.think_ms.append((ms[0], ms[1]))
            result = step(state, {0: orders[0], 1: orders[1]})
            state, events = result.state, result.events
        record.result = _result(state, failures)
    finally:
        tails = [c.close() for c in channels] + ["", ""]
        record.stderr = (tails[0], tails[1])
    record.final_state = state
    record.warnings = budget.warnings()
    return record


def _exchange(
    channels: list[Channel], messages: list[dict[str, Any]], wait_s: float
) -> tuple[list[bytes], dict[int, tuple[Failure, str]], list[int]]:
    """Send both seats their message first, so both think at once, then collect replies:
    (reply lines, failures by seat, thinking time in ms)."""
    for channel, message in zip(channels, messages, strict=True):
        channel.send(message)
    lines: list[bytes] = []
    failures: dict[int, tuple[Failure, str]] = {}
    ms: list[int] = []
    for seat, channel in enumerate(channels):
        reply = channel.receive(wait_s)
        ms.append(round(reply.ms))
        lines.append(reply.line or b"")
        if reply.line is None:
            failures[seat] = (reply.problem or Failure.CRASH, reply.detail)
    return lines, failures, ms


def _note_log(record: MatchRecord, seat: int, turn: int, text: str, limits: Limits) -> None:
    used = sum(len(t.encode()) for _, t in record.logs[seat])
    if text and used + len(text.encode()) <= limits.log_max_bytes_per_match:
        record.logs[seat].append((turn, text))


def _result(state: GameState, failures: dict[int, tuple[Failure, str]]) -> Result:
    if len(failures) == 2:
        return Result(None, "both_failed", state.turn, "; ".join(d for _, d in failures.values()))
    if failures:
        seat, (failure, detail) = next(iter(failures.items()))
        return Result(1 - seat, failure.value, state.turn, f"seat {seat}: {detail}")
    assert state.outcome is not None
    return Result(state.outcome.winner, state.outcome.reason.value, state.outcome.turns)


class _Budget:
    """Ranked time rules: count overruns and track each bot's time bank. Locally they only
    produce warnings; `run_match(enforce=True)` makes an empty bank a loss."""

    def __init__(self, limits: Limits) -> None:
        self.limits = limits
        self.bank = [limits.time_bank_ms, limits.time_bank_ms]
        self.over = [0, 0]
        self.slowest = [0, 0]
        self.out_of_time: list[int | None] = [None, None]

    def charge(self, turn: int, ms: list[int]) -> None:
        for seat in (0, 1):
            self.slowest[seat] = max(self.slowest[seat], ms[seat])
            overrun = ms[seat] - self.limits.turn_ms
            if overrun > 0:
                self.over[seat] += 1
                self.bank[seat] -= overrun
                if self.bank[seat] < 0 and self.out_of_time[seat] is None:
                    self.out_of_time[seat] = turn

    def warnings(self) -> list[str]:
        notes: list[str] = []
        for seat in (0, 1):
            if self.over[seat]:
                notes.append(
                    f"seat {seat}: {self.over[seat]} turns over the {self.limits.turn_ms} ms "
                    f"budget (slowest {self.slowest[seat]} ms)"
                )
            if (turn := self.out_of_time[seat]) is not None:
                notes.append(f"seat {seat}: would have lost on time at turn {turn} in ranked")
        return notes


def _ms_since(start: float) -> float:
    return (time.perf_counter() - start) * 1000
