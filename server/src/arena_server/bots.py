"""Users, bots and bot versions. A new version waits as `pending` until a worker validates it
in the jail; the host itself only stores the bytes."""

import sqlite3

from .queue import immediate
from .store import CODE, PY, Store

ARENA_ACCOUNT = "arena"  # owns the built-in bots, which play on the ladder as anchors


def ensure_user(conn: sqlite3.Connection, handle: str, github_id: int | None = None) -> int:
    with immediate(conn):
        conn.execute(
            "INSERT INTO users (handle, github_id) VALUES (?, ?) ON CONFLICT (handle) DO NOTHING",
            (handle, github_id),
        )
        return conn.execute("SELECT id FROM users WHERE handle = ?", (handle,)).fetchone()[0]


def login_user(conn: sqlite3.Connection, github_id: int, handle: str) -> int:
    """The user for a GitHub account, created on first login. A GitHub id and handle are all
    we keep; a renamed account keeps its user and gets the new handle."""
    with immediate(conn):
        row = conn.execute("SELECT id FROM users WHERE github_id = ?", (github_id,)).fetchone()
        if row:
            conn.execute("UPDATE users SET handle = ? WHERE id = ?", (handle, row[0]))
            return row[0]
        return conn.execute(
            "INSERT INTO users (handle, github_id) VALUES (?, ?) RETURNING id", (handle, github_id)
        ).fetchone()[0]


def create_bot(conn: sqlite3.Connection, owner_id: int, name: str) -> int:
    with immediate(conn):
        return conn.execute(
            "INSERT INTO bots (owner_id, name) VALUES (?, ?) RETURNING id", (owner_id, name)
        ).fetchone()[0]


def submit_version(conn: sqlite3.Connection, store: Store, bot_id: int, code: bytes) -> int:
    """Store the code and add a pending version. Nothing here reads or runs the code."""
    ref = store.put(CODE, code, PY)
    return _add_version(conn, bot_id, ref, "pending")


def builtin_version(conn: sqlite3.Connection, name: str) -> int:
    """The active version of a built-in bot, created on first use."""
    owner = ensure_user(conn, ARENA_ACCOUNT)
    code = f"builtin:{name}"
    row = conn.execute(
        """SELECT bv.id FROM bot_versions bv JOIN bots b ON b.id = bv.bot_id
           WHERE b.owner_id = ? AND bv.code = ? AND bv.status = 'active'""",
        (owner, code),
    ).fetchone()
    if row:
        return row[0]
    bot = conn.execute(
        "SELECT id FROM bots WHERE owner_id = ? AND name = ?", (owner, name)
    ).fetchone()
    bot_id = bot[0] if bot else create_bot(conn, owner, name)
    return _add_version(conn, bot_id, code, "active")


def pending(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT id, bot_id, code FROM bot_versions WHERE status = 'pending' ORDER BY id"
    ).fetchall()


def activate(conn: sqlite3.Connection, version_id: int) -> None:
    """Make a version the bot's live one; its earlier active version retires."""
    with immediate(conn):
        bot_id = conn.execute(
            "SELECT bot_id FROM bot_versions WHERE id = ?", (version_id,)
        ).fetchone()[0]
        conn.execute(
            "UPDATE bot_versions SET status = 'retired' WHERE bot_id = ? AND status = 'active'",
            (bot_id,),
        )
        conn.execute("UPDATE bot_versions SET status = 'active' WHERE id = ?", (version_id,))


def reject(conn: sqlite3.Connection, version_id: int, error: str) -> None:
    with immediate(conn):
        conn.execute(
            "UPDATE bot_versions SET status = 'rejected', error = ? WHERE id = ?",
            (error, version_id),
        )


def _add_version(conn: sqlite3.Connection, bot_id: int, code: str, status: str) -> int:
    with immediate(conn):
        latest = conn.execute(
            "SELECT id, n FROM bot_versions WHERE bot_id = ? ORDER BY n DESC LIMIT 1", (bot_id,)
        ).fetchone()
        return conn.execute(
            """INSERT INTO bot_versions (bot_id, n, code, parent_id, status)
               VALUES (?, ?, ?, ?, ?) RETURNING id""",
            (
                bot_id,
                (latest["n"] + 1) if latest else 1,
                code,
                latest["id"] if latest else None,
                status,
            ),
        ).fetchone()[0]


def describe(conn: sqlite3.Connection, version_ids: tuple[int, ...]) -> list[dict[str, object]]:
    """Who plays in each seat, as the viewer and the match page show it."""
    players: list[dict[str, object]] = []
    for seat, version in enumerate(version_ids):
        row = conn.execute(
            """SELECT b.id, b.name, u.handle, v.n FROM bot_versions v
               JOIN bots b ON b.id = v.bot_id JOIN users u ON u.id = b.owner_id
               WHERE v.id = ?""",
            (version,),
        ).fetchone()
        players.append(
            {"seat": seat, "version_id": version, "bot_id": row[0], "bot": row[1],
             "owner": row[2], "version": row[3]}
        )  # fmt: skip
    return players
