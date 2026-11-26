"""Keeps the ladder busy: tops the queue up with ranked pairings and reaps dead leases.

ARENA_DATA_DIR=/var/lib/arena python -m arena_server.scheduler
"""

import logging
import os
import sqlite3
import time
from pathlib import Path
from random import Random

from . import ladder, queue
from .db import connect, migrate
from .ratings import Ratings
from .settings import Settings
from .store import Store

log = logging.getLogger("arena.scheduler")


def tick(
    conn: sqlite3.Connection, store: Store, ratings: Ratings, settings: Settings, rng: Random
) -> None:
    """Reaping always runs; while the kill switch is set nothing new is queued."""
    if requeued := queue.reap(conn):
        log.warning("reaped expired leases, re-queued %s", requeued)
    if store.paused:
        return
    if added := ladder.top_up(conn, ratings, settings, rng):
        log.info("queued %d ranked matches", len(added))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = Settings.load()
    ratings = Ratings(settings)
    data = Path(os.environ["ARENA_DATA_DIR"])
    conn = connect(data / "arena.db")
    migrate(conn)
    store, rng = Store(data), Random()
    while True:
        tick(conn, store, ratings, settings, rng)
        time.sleep(settings.reap_every_s / 10)


if __name__ == "__main__":
    main()
