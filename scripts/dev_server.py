"""Local development only: the API on 127.0.0.1:8000, with a worker and the scheduler.

    uv run python scripts/dev_server.py [--turn-delay 0.05]

Then `npm run dev --prefix web`, which proxies to it. Two things here must never reach a real
server: "Log in" signs you in as `dev` without asking GitHub, and matches run with the local
runner, outside the jail. That is fine for built-in bots and your own code on your own machine.
"""

import argparse
import logging
import sqlite3
import threading
import time
from pathlib import Path
from random import Random

import uvicorn
from arena.runner import MatchRecord, run_match
from arena_engine import GameState, Rules
from arena_server import bots, ladder, queue
from arena_server.api import create_app
from arena_server.db import connect, migrate
from arena_server.ratings import Ratings
from arena_server.settings import Settings
from arena_server.store import Store
from arena_server.worker import OnTurn, Worker

DATA = Path(__file__).resolve().parent.parent / ".dev-data"


class DevGitHub:
    def authorize_url(self, state: str) -> str:
        return f"/auth/github/callback?code=dev&state={state}"

    def identify(self, code: str) -> tuple[int, str]:
        return 1, "dev"


def background(turn_delay: float) -> None:
    def play(
        players: tuple[str, str], seed: int, rules: Rules | None, on_turn: OnTurn | None
    ) -> MatchRecord:
        def slow(state: GameState) -> None:
            if on_turn:
                on_turn(state)
                time.sleep(turn_delay)  # slow enough to watch live

        return run_match(players, seed, rules, on_turn=slow)

    conn = connect(DATA / "arena.db")
    worker = Worker(conn, Store(DATA), play)
    settings = Settings.load()
    while True:
        queue.reap(conn)  # a match cut off by the last restart
        ladder.top_up(conn, Ratings(settings), settings, Random())
        if not worker.step():
            time.sleep(1)


SPARRING = {
    "rusher": "from arena.builtin.rush import RushBot\n\nclass Rusher(RushBot):\n    pass\n",
    "miner": "from arena.builtin.greedy import GreedyBot\n\nclass Miner(GreedyBot):\n    pass\n",
    "wall": "from arena.builtin.turtle import TurtleBot\n\nclass Wall(TurtleBot):\n    pass\n",
}


def seed_sparring_partners(conn: sqlite3.Connection) -> None:
    """A second player, so the ladder has someone to pair (one owner never plays itself)."""
    bots.ensure_anchors(conn)
    owner = bots.ensure_user(conn, "sparring", github_id=2)
    for name, code in SPARRING.items():
        bots.submit_version(conn, Store(DATA), bots.create_bot(conn, owner, name), code.encode())


def main() -> None:
    parser = argparse.ArgumentParser(description="API, worker and scheduler for local development")
    parser.add_argument("--turn-delay", type=float, default=0.05)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    DATA.mkdir(exist_ok=True)
    conn = connect(DATA / "arena.db")
    migrate(conn)
    if not conn.execute("SELECT 1 FROM users WHERE handle = 'sparring'").fetchone():
        seed_sparring_partners(conn)
    app = create_app(
        DATA, DevGitHub(), b"dev-only-session-secret-not-for-production", admins=frozenset({1})
    )  # the fake login (github id 1) can open /admin
    threading.Thread(target=background, args=(args.turn_delay,), daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
