"""Browser practice: one match, driven from JavaScript.

The page runs `Practice` in a Pyodide Web Worker, next to the built-in opponent. The
player's bot runs in a second worker through `PlayerBot`, which is the same harness the CLI
runs. JavaScript carries protocol lines between the two and times each reply; the rules,
the checks on replies and the record are `Match`, exactly as in `arena match`. So the
replay a practice match produces is the replay the CLI produces for the same seed and bots.

Pyodide is not a sandbox: this only ever runs the player's own code, in their own browser.
"""

import json
import traceback
from pathlib import Path
from typing import Any

from arena_engine import GameState

from .frames import end, frame, header, invalid_orders
from .harness import BotSession, load_bot
from .protocol import encode
from .replay import decode
from .replay import encode as encode_replay
from .runner import Failure, InProcessChannel, Match, Reply


class Practice:
    """The host side: the engine, the record and the built-in opponent."""

    def __init__(self, bot_path: str, opponent: str, seed: int, seat: int) -> None:
        self.seat = seat
        specs = [opponent, opponent]
        specs[seat] = bot_path
        players = (specs[0], specs[1])
        self.frames: list[dict[str, Any]] = []
        self.match = Match(players, seed, on_turn=self._seen)
        self.opponent = InProcessChannel(load_bot(opponent))
        described = [
            {"seat": s, "bot": _name(spec), "owner": "you" if s == seat else "arena"}
            for s, spec in enumerate(players)
        ]
        self.header = header(self.match.state, described)
        self.pending = self.match.start()

    def to_player(self) -> str | None:
        """The next protocol line for the player's bot, or None once the match is over."""
        return None if self.pending is None else encode(self.pending[self.seat]).decode()

    def wait_ms(self) -> float:
        """How long JavaScript waits for the player's reply before stopping its worker."""
        return self.match.wait_s * 1000

    def from_player(self, line: str | None, ms: float, problem: str, detail: str) -> None:
        """The player's reply (None if it crashed or hung), then the opponent's, then a turn."""
        assert self.pending is not None
        mine = Reply(
            line.encode() if line is not None else None,
            ms,
            Failure(problem) if problem else None,
            detail,
        )
        self.opponent.send(self.pending[1 - self.seat])
        theirs = self.opponent.receive(self.match.wait_s)
        replies = [theirs, theirs]
        replies[self.seat] = mine
        self.pending = self.match.advance(replies)

    def take_frames(self) -> str:
        """The frames since the last call, as JSON: the viewer's list keeps growing."""
        taken, self.frames = self.frames, []
        return json.dumps(taken)

    def finish(self, player_stderr: str) -> str:
        """Everything the page shows once the match is over, as JSON."""
        record = self.match.record
        record.stderr = (player_stderr, self.opponent.close())
        replay = decode(self.replay())
        return json.dumps(
            {
                "end": end(record.result),
                "detail": record.result.detail,
                "logs": record.logs[self.seat],
                "invalid": invalid_orders(replay, self.seat),
                "warnings": record.warnings,
            }
        )

    def replay(self) -> bytes:
        return encode_replay(self.match.record)

    def _seen(self, state: GameState) -> None:
        self.frames.append(frame(state))


class PlayerBot:
    """The bot side, in the player's own worker: the CLI's harness, one line at a time."""

    def __init__(self, path: str) -> None:
        self.error = ""
        self.session: BotSession | None = None
        try:
            self.session = BotSession(load_bot(path))
        except Exception:
            self.error = traceback.format_exc()

    def answer(self, line: str) -> str | None:
        """The reply line, or None if the bot failed (the traceback is in `error`)."""
        if self.session is None:
            return None
        try:
            return encode(self.session.handle(json.loads(line))).decode()
        except Exception:
            self.error = traceback.format_exc()
            self.session = None
            return None


def _name(spec: str) -> str:
    return spec.removeprefix("builtin:") if spec.startswith("builtin:") else Path(spec).stem
