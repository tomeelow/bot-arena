"""Upload validation through the real jail: the server never runs an upload anywhere else."""

from pathlib import Path

import pytest
from arena_sandbox import ranked_match
from arena_server import bots
from arena_server.db import connect, migrate
from arena_server.store import Store
from arena_server.worker import Worker

ADVERSARIAL = Path(__file__).parent.parent / "adversarial"
FINE = b"from arena import Bot\n\nclass Fine(Bot):\n    def act(self, obs):\n        return []\n"


def jailed(players, seed, rules):
    return ranked_match(players, seed, rules=rules)


@pytest.mark.parametrize(
    ("code", "status", "reason"),
    [
        (FINE, "active", None),
        ((ADVERSARIAL / "import_bomb.py").read_bytes(), "rejected", "memory"),
        ((ADVERSARIAL / "early_exit.py").read_bytes(), "rejected", "crash"),
    ],
)
def test_uploads_are_validated_in_the_jail(tmp_path, code, status, reason):
    db = connect(tmp_path / "arena.db")
    migrate(db)
    store = Store(tmp_path / "data")
    owner = bots.ensure_user(db, "eve", github_id=5)
    version = bots.submit_version(db, store, bots.create_bot(db, owner, "upload"), code)
    Worker(db, store, jailed).step()
    row = db.execute("SELECT status, error FROM bot_versions WHERE id = ?", (version,)).fetchone()
    assert row["status"] == status
    if reason:
        assert row["error"].startswith(reason)
