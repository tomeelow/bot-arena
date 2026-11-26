import sqlite3

from arena_server import queue


def must_claim(db: sqlite3.Connection, worker: str, lease_s: float = 60) -> queue.Claim:
    claim = queue.claim(db, worker, lease_s)
    assert claim is not None, "the queue was empty"
    return claim
