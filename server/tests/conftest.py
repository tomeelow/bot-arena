import pytest
from arena_server.db import connect, migrate
from arena_server.store import Store


@pytest.fixture
def db(tmp_path):
    conn = connect(tmp_path / "arena.db")
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "data")
