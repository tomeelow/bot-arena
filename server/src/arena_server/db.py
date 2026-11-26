"""SQLite (ADR-004): one database file, WAL mode, plain-SQL migrations applied in order."""

import sqlite3
from importlib.resources import files
from pathlib import Path


def connect(path: Path) -> sqlite3.Connection:
    """A connection in autocommit mode: every write says where its transaction begins. The API
    may hand a request's connection between threads, but never shares one between requests."""
    conn = sqlite3.connect(path, timeout=30, autocommit=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    """Apply every migration newer than the database's user_version. Returns the version."""
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    scripts = sorted(
        (int(f.name.split("_")[0]), f)
        for f in files("arena_server").joinpath("migrations").iterdir()
        if f.name.endswith(".sql")
    )
    for version, script in scripts:
        if version > current:
            conn.executescript(
                f"BEGIN IMMEDIATE; {script.read_text()}; PRAGMA user_version = {version}; COMMIT;"
            )
            current = version
    return current
