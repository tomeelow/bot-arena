"""A worker: validates pending bot versions and plays queued matches, one at a time.

    ARENA_DATA_DIR=/var/lib/arena python -m arena_server.worker

A match is recorded only after its replay is stored and re-simulates to the recorded final
state. Anything that goes wrong on our side voids the match: never a rated result.
"""

import json
import logging
import os
import socket
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from random import Random

from arena import frames
from arena.protocol import truncate
from arena.replay import encode, load
from arena.runner import Failure, MatchRecord
from arena_engine import ENGINE_VERSION, GameState, Rules

from . import bots, ladder, queue
from .db import connect, migrate
from .ratings import Ratings
from .settings import Settings
from .store import CODE, PY, REPLAY, REPLAYS, Store

log = logging.getLogger("arena.worker")

type OnTurn = Callable[[GameState], None]
type Play = Callable[[tuple[str, str], int, Rules | None, OnTurn | None], MatchRecord]
BOT_FAULTS = {f.value for f in Failure}
SMOKE_OPPONENT = "builtin:random"


@dataclass
class Worker:
    conn: sqlite3.Connection
    store: Store
    play: Play
    settings: Settings = field(default_factory=Settings.load)
    worker_id: str = field(default_factory=lambda: f"{socket.gethostname()}:{os.getpid()}")
    rng: Random = field(default_factory=Random)

    def __post_init__(self) -> None:
        self.ratings = Ratings(self.settings)

    def step(self) -> bool:
        """Do one piece of work: validate a pending version, else play a queued match.
        Returns False when there was nothing to do, or the kill switch is set."""
        if self.store.paused:
            return False
        if pending := bots.pending(self.conn):
            self.validate(pending[0]["id"], pending[0]["code"])
            return True
        claim = queue.claim(self.conn, self.worker_id, self.settings.lease_s)
        if claim is None:
            return False
        self.play_claim(claim)
        return True

    def validate(self, version_id: int, code: str) -> None:
        """A short smoke match against builtin:random, in the jail. A bot that fails it
        (crash, timeout, memory, bad output) is rejected and its owner sees why."""
        rules = Rules(max_turns=self.settings.smoke_turns)
        record = self.play((self.spec(code), SMOKE_OPPONENT), version_id, rules, None)
        result = record.result
        if (result.reason in BOT_FAULTS and result.winner != 0) or result.reason == "both_failed":
            detail = f"{result.reason}: {result.detail}\n{record.stderr[0]}".strip()
            bots.reject(self.conn, version_id, truncate(detail, self.settings.error_max_bytes))
            log.info("version %d rejected: %s", version_id, result.reason)
        else:
            bots.activate(self.conn, version_id)
            placed = ladder.place(self.conn, version_id, self.settings, self.rng)
            log.info("version %d active, %d placement matches queued", version_id, len(placed))

    def play_claim(self, claim: queue.Claim) -> None:
        live: LiveFile | None = None
        try:
            if claim.engine_version != ENGINE_VERSION:
                raise RuntimeError(f"queued for engine {claim.engine_version}")
            players = (self.spec(claim.codes[0]), self.spec(claim.codes[1]))
            live = LiveFile(
                self.store.live(claim.match_id), bots.describe(self.conn, claim.version_ids)
            )
            record = self.play(players, claim.seed, None, live.turn)
            replay = self.store.put(REPLAYS, encode(record), REPLAY)
            load(self.store.path(REPLAYS, replay, REPLAY))  # re-simulates; raises on mismatch
            logs = self.store.logs(claim.match_id)
            logs.parent.mkdir(parents=True, exist_ok=True)
            logs.write_text(json.dumps({"0": record.logs[0], "1": record.logs[1]}))
        except Exception as e:
            log.exception("platform_error in match %d", claim.match_id)
            queue.void(self.conn, claim.match_id, f"platform_error: {e!r}"[:500])
            if live:
                live.close({"type": "void"})
            return
        live.close(frames.end(record.result))
        if queue.finish(
            self.conn, claim.match_id, self.worker_id, record.result, replay, self.ratings
        ):
            log.info(
                "match %d: %s, turn %d",
                claim.match_id,
                record.result.reason,
                record.result.turns,
            )
        else:
            log.warning(
                "match %d finished after losing its lease; result discarded", claim.match_id
            )

    def spec(self, code: str) -> str:
        """What the runner is handed: a built-in's name, or the stored file's path."""
        return code if code.startswith("builtin:") else str(self.store.path(CODE, code, PY))

    def run(self) -> None:
        next_reap = 0.0
        while True:
            if time.monotonic() >= next_reap:
                if requeued := queue.reap(self.conn):
                    log.warning("reaped expired leases, re-queued %s", requeued)
                next_reap = time.monotonic() + self.settings.reap_every_s
            if not self.step():
                time.sleep(self.settings.idle_sleep_s)


def main() -> None:
    from arena_sandbox import ranked_match

    def play(
        players: tuple[str, str], seed: int, rules: Rules | None, on_turn: OnTurn | None
    ) -> MatchRecord:
        return ranked_match(players, seed, rules=rules, on_turn=on_turn)

    data = Path(os.environ["ARENA_DATA_DIR"])
    conn = connect(data / "arena.db")
    migrate(conn)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    Worker(conn, Store(data), play).run()


if __name__ == "__main__":
    main()


class LiveFile:
    """Appends a match's frames as it is played. Viewers tail this file (api.py)."""

    def __init__(self, path: Path, players: list[dict[str, object]]) -> None:
        self.path = path
        self.players = players
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("w")

    def turn(self, state: GameState) -> None:
        if state.turn == 0:
            self._write(frames.header(state, self.players))
        self._write(frames.frame(state))

    def close(self, last: dict[str, object]) -> None:
        self._write(last)
        self.file.close()

    def _write(self, line: dict[str, object]) -> None:
        self.file.write(json.dumps(line, separators=(",", ":")) + "\n")
        self.file.flush()
