"""The API: login, limits, private logs, frames and live viewing, through real HTTP."""

import threading
import time
from contextlib import ExitStack
from dataclasses import replace
from urllib.parse import parse_qs, urlparse

import plays
import pytest
from arena_server import bots, queue
from arena_server.api import create_app
from arena_server.db import connect
from arena_server.settings import Settings
from arena_server.store import Store
from arena_server.worker import Worker
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

SETTINGS = replace(
    Settings.load(),
    uploads_per_day=2,
    comparisons_per_day=1,
    upload_max_bytes=1000,
    live_poll_s=0.01,
    viewers_per_match=3,
)
FINE = b"from arena import Bot\n\nclass Fine(Bot):\n    def act(self, obs):\n        return []\n"
CHATTY = FINE.replace(b"return []", b"print('secret plan')\n        return []")
SLOW = FINE.replace(b"return []", b"__import__('time').sleep(0.02)\n        return []")


class FakeGitHub:
    def __init__(self) -> None:
        self.users = {
            "code-ada": (101, "ada"),
            "code-bob": (102, "bob"),
            "code-ada-renamed": (101, "ada2"),
        }

    def authorize_url(self, state: str) -> str:
        return f"https://github.example/authorize?state={state}"

    def identify(self, code: str) -> tuple[int, str]:
        return self.users[code]


@pytest.fixture
def data(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def app(data):
    return create_app(data, FakeGitHub(), b"s" * 32, SETTINGS)


def client(app) -> TestClient:
    return TestClient(app, base_url="https://testserver")


def login(c: TestClient, code: str):
    start = c.get("/auth/github/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    params = {"code": code, "state": state}
    done = c.get("/auth/github/callback", params=params, follow_redirects=False)
    assert done.status_code == 302
    return done


def new_bot(c: TestClient, name: str = "mine") -> int:
    r = c.post("/api/bots", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def played_match(data, code: bytes = FINE) -> int:
    """A finished match between ada's bot (seat 0) and a built-in, played by a worker."""
    db = connect(data / "arena.db")
    owner = bots.login_user(db, 101, "ada")
    version = bots.submit_version(db, Store(data), bots.create_bot(db, owner, "logs"), code)
    bots.activate(db, version)
    match = queue.enqueue(db, "ranked", (version, bots.builtin_version(db, "rush")), seed=4)
    Worker(db, Store(data), plays.local).step()
    return match


def test_health_and_published_openapi(app):
    c = client(app)
    assert c.get("/health").json()["status"] == "ok"
    paths = c.get("/openapi.json").json()["paths"]
    for path in (
        "/api/ladder",
        "/api/bots/{bot_id}/versions",
        "/api/compare",
        "/api/matches/{match_id}/frames",
        "/api/matches/{match_id}/logs/{seat}",
    ):
        assert path in paths


def test_login_keeps_only_a_github_id_and_handle(app, data):
    login(client(app), "code-ada")
    db = connect(data / "arena.db")
    assert [r[1] for r in db.execute("PRAGMA table_info(users)")] == [
        "id",
        "github_id",
        "handle",
        "created_at",
    ]
    assert [tuple(r) for r in db.execute("SELECT github_id, handle FROM users")] == [(101, "ada")]
    login(client(app), "code-ada-renamed")
    assert [tuple(r) for r in db.execute("SELECT github_id, handle FROM users")] == [(101, "ada2")]


def test_session_cookies_are_http_only_secure_and_lax(app):
    done = login(client(app), "code-bob")
    session = next(h for h in done.headers.get_list("set-cookie") if h.startswith("session="))
    assert "HttpOnly" in session and "Secure" in session and "samesite=lax" in session.lower()


def test_a_login_that_was_not_started_here_is_refused(app):
    c = client(app)
    c.get("/auth/github/login", follow_redirects=False)
    r = c.get("/auth/github/callback", params={"code": "code-ada", "state": "forged"})
    assert r.status_code == 400


def test_uploads_need_a_login_ownership_a_size_limit_and_a_daily_limit(app):
    ada, bob = client(app), client(app)
    assert ada.post("/api/bots", json={"name": "x"}).status_code == 401
    login(ada, "code-ada")
    login(bob, "code-bob")
    bot = new_bot(ada)
    assert bob.post(f"/api/bots/{bot}/versions", content=FINE).status_code == 403
    assert ada.post(f"/api/bots/{bot}/versions", content=b"x" * 2000).status_code == 413
    for _ in range(SETTINGS.uploads_per_day):
        r = ada.post(f"/api/bots/{bot}/versions", content=FINE)
        assert (r.status_code, r.json()["status"]) == (202, "pending")
    assert ada.post(f"/api/bots/{bot}/versions", content=FINE).status_code == 429


def test_comparisons_are_your_own_and_rate_limited(app):
    ada, bob = client(app), client(app)
    login(ada, "code-ada")
    login(bob, "code-bob")
    bot = new_bot(ada)
    v1 = ada.post(f"/api/bots/{bot}/versions", content=FINE).json()["version_id"]
    v2 = ada.post(f"/api/bots/{bot}/versions", content=FINE + b"#2").json()["version_id"]
    body = {"challenger": v2, "incumbent": v1, "seed_pairs": 2}
    assert bob.post("/api/compare", json=body).status_code == 403
    assert ada.post("/api/compare", json={**body, "seed_pairs": 999}).status_code == 422
    first = ada.post("/api/compare", json=body)
    assert (first.status_code, first.json()["pending"]) == (202, 4)
    assert ada.post("/api/compare", json=body).status_code == 429


def test_logs_are_visible_only_to_the_bots_owner(app, data):
    match = played_match(data, CHATTY)
    ada, bob, anon = client(app), client(app), client(app)
    login(ada, "code-ada")
    login(bob, "code-bob")
    assert anon.get(f"/api/matches/{match}/logs/0").status_code == 401
    assert bob.get(f"/api/matches/{match}/logs/0").status_code == 403
    assert ada.get(f"/api/matches/{match}/logs/1").status_code == 403  # the built-in's
    logs = ada.get(f"/api/matches/{match}/logs/0")
    assert logs.status_code == 200
    assert logs.json()[0] == [0, "secret plan\n"]


def test_frames_come_from_the_live_file_or_the_replay_alike(app, data):
    match = played_match(data)
    c = client(app)
    lines = c.get(f"/api/matches/{match}/frames").json()
    turns = c.get(f"/api/matches/{match}").json()["result"]["turns"]
    assert [line["type"] for line in lines] == ["header"] + ["frame"] * (turns + 1) + ["end"]
    assert [line["turn"] for line in lines[1:-1]] == list(range(turns + 1))
    Store(data).live(match).unlink()
    assert c.get(f"/api/matches/{match}/frames").json() == lines


def collect(c: TestClient, match: int, out: list[str], start: threading.Event) -> None:
    start.wait()
    with c.websocket_connect(f"/ws/matches/{match}") as ws:
        try:
            while True:
                out.append(ws.receive_text())
        except WebSocketDisconnect:
            pass


def test_viewers_and_a_late_joiner_all_see_the_whole_match_from_turn_0(app, data):
    db = connect(data / "arena.db")
    owner = bots.login_user(db, 101, "ada")
    slow = bots.submit_version(db, Store(data), bots.create_bot(db, owner, "slow"), SLOW)
    bots.activate(db, slow)
    match = queue.enqueue(db, "ranked", (slow, bots.builtin_version(db, "rush")), seed=4)

    now, mid_match = threading.Event(), threading.Event()
    now.set()
    first: list[str] = []
    second: list[str] = []
    late: list[str] = []
    viewers = [
        threading.Thread(target=collect, args=(client(app), match, first, now)),
        threading.Thread(target=collect, args=(client(app), match, second, now)),
        threading.Thread(target=collect, args=(client(app), match, late, mid_match)),
    ]
    for v in viewers:
        v.start()
    worker = Worker(connect(data / "arena.db"), Store(data), plays.local)
    play = threading.Thread(target=worker.step)
    play.start()
    while len(first) < 30:
        time.sleep(0.01)
    mid_match.set()
    play.join()
    for v in viewers:
        v.join(timeout=30)
    assert first == second == late
    assert '"type":"header"' in first[0]
    assert '"turn":0' in first[1]
    assert '"type":"end"' in first[-1]


def test_too_many_viewers_are_turned_away_and_leaving_frees_a_place(app, data):
    db = connect(data / "arena.db")
    pair = (bots.builtin_version(db, "rush"), bots.builtin_version(db, "greedy"))
    match = queue.enqueue(db, "ranked", pair, seed=1)  # stays queued: viewers wait
    with ExitStack() as stack:
        for _ in range(SETTINGS.viewers_per_match):
            stack.enter_context(client(app).websocket_connect(f"/ws/matches/{match}"))
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            client(app).websocket_connect(f"/ws/matches/{match}") as extra,
        ):
            extra.receive_text()
        assert refused.value.code == 1013
    time.sleep(0.2)  # the server notices the departures
    with client(app).websocket_connect(f"/ws/matches/{match}"):
        pass  # accepted again


def test_the_ladder_shows_intervals_and_ranks(app, data):
    played_match(data)
    rows = client(app).get("/api/ladder").json()
    assert rows and all(r["low"] < r["mu"] < r["high"] for r in rows)
    assert [r["rank"] for r in rows] == list(range(1, len(rows) + 1))
