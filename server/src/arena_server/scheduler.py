"""Keeps the ladder busy: tops the queue up with ranked pairings and reaps dead leases.

ARENA_DATA_DIR=/var/lib/arena python -m arena_server.scheduler
"""

import logging
import os
import time
from pathlib import Path
from random import Random

from . import ladder, queue
from .db import connect, migrate
from .ratings import Ratings
from .settings import Settings

log = logging.getLogger("arena.scheduler")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    settings = Settings.load()
    ratings = Ratings(settings)
    conn = connect(Path(os.environ["ARENA_DATA_DIR"]) / "arena.db")
    migrate(conn)
    rng = Random()
    while True:
        if requeued := queue.reap(conn):
            log.warning("reaped expired leases, re-queued %s", requeued)
        if added := ladder.top_up(conn, ratings, settings, rng):
            log.info("queued %d ranked matches", len(added))
        time.sleep(settings.reap_every_s / 10)


if __name__ == "__main__":
    main()
