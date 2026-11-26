"""The HTTP and websocket API: a thin layer over the database and the stores.

    ARENA_DATA_DIR=... GITHUB_CLIENT_ID=... GITHUB_CLIENT_SECRET=... SESSION_SECRET=... \
        uvicorn --factory arena_server.api:app_from_env
"""

import asyncio
import json
import os
import secrets
import sqlite3
from collections import Counter
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from random import Random
from typing import Annotated, Any

from arena.replay import load
from arena.runner import Result
from arena_engine import ENGINE_VERSION
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
)
from fastapi import Path as PathParam
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse

from . import bots, compare, frames, ladder
from .auth import GitHub, GitHubOAuth, Sessions
from .db import connect, migrate
from .queue import immediate
from .ratings import Ratings, history, stored
from .schemas import (
    Account,
    BotView,
    CompareRequest,
    ComparisonView,
    Created,
    Health,
    InvalidOrderView,
    LadderRow,
    MatchSummary,
    MatchView,
    MyBot,
    NewBot,
    Outcome,
    Player,
    RatingPoint,
    Upload,
    VersionView,
)
from .settings import Settings
from .store import REPLAY, REPLAYS, Store

SESSION, OAUTH_STATE = "session", "oauth_state"
LAST = ('"type":"end"', '"type":"void"')  # a live file is complete once one of these is written


def db(request: Request) -> Iterator[sqlite3.Connection]:
    with closing(connect(request.app.state.db_path)) as conn:
        yield conn


def current_user(request: Request) -> int | None:
    return request.app.state.sessions.verify(request.cookies.get(SESSION))


def logged_in(user: Annotated[int | None, Depends(current_user)]) -> int:
    if user is None:
        raise HTTPException(401, "log in first")
    return user


DB = Annotated[sqlite3.Connection, Depends(db)]
Me = Annotated[int, Depends(logged_in)]
MaybeMe = Annotated[int | None, Depends(current_user)]
Seat = Annotated[int, PathParam(ge=0, le=1)]


def create_app(
    data: Path, github: GitHub, session_secret: bytes, settings: Settings | None = None
) -> FastAPI:
    settings = settings or Settings.load()
    ratings = Ratings(settings)
    sessions = Sessions(session_secret, settings.session_max_age_s)
    store = Store(data)
    db_path = data / "arena.db"
    data.mkdir(parents=True, exist_ok=True)
    with closing(connect(db_path)) as conn:
        migrate(conn)
    app = FastAPI(title="Bot Arena", version=ENGINE_VERSION)
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.state.db_path = db_path
    app.state.sessions = sessions
    viewers: Counter[int] = Counter()
    rng = Random()

    @app.get("/health")
    def health() -> Health:
        return Health(status="ok", engine_version=ENGINE_VERSION)

    @app.get("/api/me")
    def get_me(conn: DB, me: Me) -> Account:
        handle = conn.execute("SELECT handle FROM users WHERE id = ?", (me,)).fetchone()[0]
        rows = conn.execute("SELECT id, name FROM bots WHERE owner_id = ? ORDER BY id", (me,))
        return Account(handle=handle, bots=[MyBot(id=r["id"], name=r["name"]) for r in rows])

    @app.get("/api/matches")
    def list_matches(
        conn: DB,
        status: Annotated[str, Query(pattern="^(running|done)$")] = "done",
        limit: Annotated[int, Query(ge=1, le=50)] = 20,
    ) -> list[MatchSummary]:
        """Matches being played now, or the latest finished ones."""
        rows = conn.execute(
            "SELECT id FROM matches WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit)
        ).fetchall()
        return _summaries(conn, [r[0] for r in rows])

    @app.get("/api/ladder")
    def get_ladder(conn: DB) -> list[LadderRow]:
        board = ladder.leaderboard(conn, ratings)
        rows = []
        for s, below in zip(board, [*board[1:], None], strict=True):
            e, r = s.entry, s.entry.rating
            rows.append(
                LadderRow(
                    rank=s.rank, version_id=e.version_id, bot_id=e.bot_id, bot=e.bot,
                    owner=e.handle, mu=r.mu, sigma=r.sigma, score=s.score,
                    low=r.mu - 2 * r.sigma, high=r.mu + 2 * r.sigma, games=r.games,
                    provisional=s.provisional,
                    p_above_next=ratings.p_stronger(r, below.entry.rating) if below else None,
                )
            )  # fmt: skip
        return rows

    @app.get("/api/bots/{bot_id}")
    def get_bot(bot_id: int, conn: DB, me: MaybeMe) -> BotView:
        bot = conn.execute(
            """SELECT b.id, b.name, b.owner_id, u.handle FROM bots b
               JOIN users u ON u.id = b.owner_id WHERE b.id = ?""",
            (bot_id,),
        ).fetchone()
        if bot is None:
            raise HTTPException(404, "no such bot")
        table = stored(conn)
        rows = conn.execute(
            "SELECT id, n, status, error FROM bot_versions WHERE bot_id = ? ORDER BY n DESC",
            (bot_id,),
        ).fetchall()
        versions = [
            VersionView(
                id=v["id"], n=v["n"], status=v["status"],
                mu=table[v["id"]].mu if v["id"] in table else None,
                sigma=table[v["id"]].sigma if v["id"] in table else None,
                games=table[v["id"]].games if v["id"] in table else 0,
                error=v["error"] if me == bot["owner_id"] else None,
            )
            for v in rows
        ]  # fmt: skip
        return BotView(
            id=bot["id"],
            name=bot["name"],
            owner=bot["handle"],
            versions=versions,
            recent_matches=_recent(conn, [v["id"] for v in rows]),
        )

    @app.get("/api/bots/{bot_id}/history")
    def get_history(bot_id: int, conn: DB) -> list[RatingPoint]:
        """Each version's rating after every rated game it played, in order."""
        versions = {
            r[0] for r in conn.execute("SELECT id FROM bot_versions WHERE bot_id = ?", (bot_id,))
        }
        if not versions:
            raise HTTPException(404, "no such bot")
        return [
            RatingPoint(match_id=m, version_id=v, mu=r.mu, sigma=r.sigma)
            for m, v, r in history(conn, ratings, versions)
        ]

    @app.post("/api/bots", status_code=201)
    def new_bot(body: NewBot, conn: DB, me: Me) -> Created:
        try:
            return Created(id=bots.create_bot(conn, me, body.name))
        except sqlite3.IntegrityError:
            raise HTTPException(409, "you already have a bot with that name") from None

    @app.post("/api/bots/{bot_id}/versions", status_code=202)
    async def upload(bot_id: int, request: Request, conn: DB, me: Me) -> Upload:
        _own_bot(conn, bot_id, me)
        code = bytearray()
        async for chunk in request.stream():
            code += chunk
            if len(code) > settings.upload_max_bytes:
                raise HTTPException(413, f"a bot is at most {settings.upload_max_bytes} bytes")
        if not code:
            raise HTTPException(400, "send the bot's .py file as the request body")
        today = conn.execute(
            """SELECT count(*) FROM bot_versions v JOIN bots b ON b.id = v.bot_id
               WHERE b.owner_id = ? AND v.created_at >= datetime('now', '-1 day')""",
            (me,),
        ).fetchone()[0]
        if today >= settings.uploads_per_day:
            raise HTTPException(429, f"at most {settings.uploads_per_day} uploads a day")
        version = bots.submit_version(conn, store, bot_id, bytes(code))
        return Upload(version_id=version, status="pending")

    @app.post("/api/compare", status_code=202)
    def request_comparison(body: CompareRequest, conn: DB, me: Me) -> ComparisonView:
        if body.seed_pairs > settings.compare_max_seed_pairs:
            raise HTTPException(422, f"at most {settings.compare_max_seed_pairs} seed pairs")
        if _version_owner(conn, body.challenger) != me:
            raise HTTPException(403, "you can only compare your own versions")
        if _version_owner(conn, body.incumbent) is None:
            raise HTTPException(404, "no such version")
        today = conn.execute(
            """SELECT count(*) FROM comparisons
               WHERE requester_id = ? AND created_at >= datetime('now', '-1 day')""",
            (me,),
        ).fetchone()[0]
        if today >= settings.comparisons_per_day:
            raise HTTPException(429, f"at most {settings.comparisons_per_day} comparisons a day")
        with immediate(conn):
            comparison_id = conn.execute(
                """INSERT INTO comparisons (requester_id, challenger_id, incumbent_id)
                   VALUES (?, ?, ?) RETURNING id""",
                (me, body.challenger, body.incumbent),
            ).fetchone()[0]
        compare.request(conn, body.challenger, body.incumbent, body.seed_pairs, rng)
        return _comparison(conn, comparison_id)

    @app.get("/api/compare/{comparison_id}")
    def get_comparison(comparison_id: int, conn: DB) -> ComparisonView:
        return _comparison(conn, comparison_id)

    @app.get("/api/matches/{match_id}")
    def get_match(match_id: int, conn: DB) -> MatchView:
        m = conn.execute(
            """SELECT m.id, m.kind, m.status, m.seed, m.engine_version, m.void_reason,
                      r.winner_seat, r.end_reason, r.turns
               FROM matches m LEFT JOIN results r ON r.match_id = m.id WHERE m.id = ?""",
            (match_id,),
        ).fetchone()
        if m is None:
            raise HTTPException(404, "no such match")
        players = [Player(**p) for p in _players(conn, match_id)]
        result = (
            Outcome(winner_seat=m["winner_seat"], reason=m["end_reason"], turns=m["turns"])
            if m["end_reason"]
            else None
        )
        return MatchView(
            id=m["id"], kind=m["kind"], status=m["status"], seed=m["seed"],
            engine_version=m["engine_version"], players=players, result=result,
            void_reason=m["void_reason"],
        )  # fmt: skip

    @app.get("/api/matches/{match_id}/frames")
    def get_frames(match_id: int, conn: DB) -> list[dict[str, Any]]:
        """The whole match for the viewer: a header, one frame per turn, and the result."""
        lines = _complete_live(match_id)
        if lines is None:
            lines = _frames_from_replay(conn, match_id)
        return lines

    @app.get("/api/matches/{match_id}/logs/{seat}")
    def get_logs(match_id: int, seat: Seat, conn: DB, me: Me) -> list[tuple[int, str]]:
        _own_seat(conn, match_id, seat, me)
        path = store.logs(match_id)
        if not path.exists():
            raise HTTPException(404, "no logs for this match")
        return [(turn, text) for turn, text in json.loads(path.read_text())[str(seat)]]

    @app.get("/api/matches/{match_id}/invalid/{seat}")
    def get_invalid_orders(match_id: int, seat: Seat, conn: DB, me: Me) -> list[InvalidOrderView]:
        """The orders the engine refused from this seat: owner only, like the logs."""
        _own_seat(conn, match_id, seat, me)
        replay = load(store.path(REPLAYS, _replay_sha(conn, match_id), REPLAY))
        return [InvalidOrderView(turn=t, reason=r) for t, r in frames.invalid_orders(replay, seat)]

    @app.websocket("/ws/matches/{match_id}")
    async def watch(websocket: WebSocket, match_id: int) -> None:
        """The match so far, then each turn as it is played; a late joiner starts at turn 0."""
        if (
            viewers.total() >= settings.viewers_total
            or viewers[match_id] >= settings.viewers_per_match
        ):
            await websocket.close(code=1013, reason="too many viewers")
            return
        viewers[match_id] += 1
        await websocket.accept()
        # Viewers only listen, so the stream alone would never notice one leaving: watch for
        # the disconnect too, so an abandoned socket frees its place at once.
        stream = asyncio.create_task(_stream(websocket, match_id))
        leaving = asyncio.create_task(websocket.receive())
        try:
            await asyncio.wait({stream, leaving}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (stream, leaving):
                task.cancel()
            viewers[match_id] -= 1

    async def _stream(websocket: WebSocket, match_id: int) -> None:
        path = store.live(match_id)
        waited = 0.0
        while not path.exists():
            with closing(connect(db_path)) as conn:
                row = conn.execute("SELECT status FROM matches WHERE id = ?", (match_id,))
                status = (row.fetchone() or [None])[0]
                if status is None or status == "void":
                    await websocket.close(code=1008, reason=f"match is {status or 'unknown'}")
                    return
                if status == "done":  # played before live files existed, or pruned since
                    for line in _frames_from_replay(conn, match_id):
                        await websocket.send_json(line)
                    await websocket.close()
                    return
            if waited > settings.live_wait_s:
                await websocket.close(code=1013, reason="match has not started")
                return
            await asyncio.sleep(settings.live_poll_s)
            waited += settings.live_poll_s
        with path.open() as f:
            while True:
                position = f.tell()
                line = f.readline()
                if not line.endswith("\n"):  # nothing new yet, or half a line: wait
                    f.seek(position)
                    await asyncio.sleep(settings.live_poll_s)
                    continue
                await websocket.send_text(line.rstrip("\n"))
                if any(marker in line for marker in LAST):
                    await websocket.close()
                    return

    @app.get("/auth/github/login")
    def login() -> RedirectResponse:
        state = secrets.token_urlsafe(24)
        response = RedirectResponse(github.authorize_url(state), status_code=302)
        response.set_cookie(
            OAUTH_STATE, state, max_age=600, httponly=True, secure=True, samesite="lax"
        )
        return response

    @app.get("/auth/github/callback")
    def callback(code: str, state: str, request: Request, conn: DB) -> RedirectResponse:
        expected = request.cookies.get(OAUTH_STATE)
        if not expected or not secrets.compare_digest(expected, state):
            raise HTTPException(400, "login expired or was not started here; try again")
        try:
            github_id, handle = github.identify(code)
        except Exception:
            raise HTTPException(502, "GitHub did not confirm the login") from None
        user = bots.login_user(conn, github_id, handle)
        response = RedirectResponse("/", status_code=302)
        response.set_cookie(
            SESSION, sessions.issue(user), max_age=settings.session_max_age_s,
            httponly=True, secure=True, samesite="lax",
        )  # fmt: skip
        response.delete_cookie(OAUTH_STATE)
        return response

    @app.post("/auth/logout", status_code=204)
    def logout() -> Response:
        response = Response(status_code=204)
        response.delete_cookie(SESSION)
        return response

    def _complete_live(match_id: int) -> list[dict[str, Any]] | None:
        path = store.live(match_id)
        if not path.exists():
            return None
        lines = path.read_text().splitlines()
        if not lines or not any(marker in lines[-1] for marker in LAST):
            return None
        return [json.loads(line) for line in lines]

    def _frames_from_replay(conn: sqlite3.Connection, match_id: int) -> list[dict[str, Any]]:
        replay = load(store.path(REPLAYS, _replay_sha(conn, match_id), REPLAY))
        result = Result(**replay.data["result"])
        return [
            frames.header(replay.states[0], _players(conn, match_id)),
            *(frames.frame(s) for s in replay.states),
            frames.end(result),
        ]

    return app


def _recent(conn: sqlite3.Connection, version_ids: list[int]) -> list[MatchSummary]:
    if not version_ids:
        return []
    marks = ",".join("?" * len(version_ids))
    rows = conn.execute(
        f"""SELECT DISTINCT match_id FROM match_players WHERE bot_version_id IN ({marks})
            ORDER BY match_id DESC LIMIT 20""",
        version_ids,
    ).fetchall()
    return _summaries(conn, [r[0] for r in rows])


def _summaries(conn: sqlite3.Connection, match_ids: list[int]) -> list[MatchSummary]:
    summaries = []
    for match_id in match_ids:
        m = conn.execute(
            """SELECT m.id, m.kind, m.status, r.winner_seat, r.end_reason FROM matches m
               LEFT JOIN results r ON r.match_id = m.id WHERE m.id = ?""",
            (match_id,),
        ).fetchone()
        summaries.append(
            MatchSummary(
                id=m["id"], kind=m["kind"], status=m["status"],
                players=[f"{p['owner']}/{p['bot']}" for p in _players(conn, m["id"])],
                winner_seat=m["winner_seat"], reason=m["end_reason"],
            )
        )  # fmt: skip
    return summaries


def _players(conn: sqlite3.Connection, match_id: int) -> list[dict[str, Any]]:
    seats = conn.execute(
        "SELECT bot_version_id FROM match_players WHERE match_id = ? ORDER BY seat", (match_id,)
    ).fetchall()
    return bots.describe(conn, tuple(r[0] for r in seats))


def _bot_owner(conn: sqlite3.Connection, bot_id: int) -> int | None:
    row = conn.execute("SELECT owner_id FROM bots WHERE id = ?", (bot_id,)).fetchone()
    return row[0] if row else None


def _own_seat(conn: sqlite3.Connection, match_id: int, seat: int, me: int) -> None:
    players = _players(conn, match_id)
    if not players:
        raise HTTPException(404, "no such match")
    if _bot_owner(conn, players[seat]["bot_id"]) != me:
        raise HTTPException(403, "only the bot's owner sees this")


def _replay_sha(conn: sqlite3.Connection, match_id: int) -> str:
    row = conn.execute("SELECT replay_sha256 FROM results WHERE match_id = ?", (match_id,))
    sha = row.fetchone()
    if sha is None:
        raise HTTPException(409, "the match isn't finished; watch it on the websocket")
    return sha[0]


def _own_bot(conn: sqlite3.Connection, bot_id: int, me: int) -> None:
    owner = _bot_owner(conn, bot_id)
    if owner is None:
        raise HTTPException(404, "no such bot")
    if owner != me:
        raise HTTPException(403, "that bot isn't yours")


def _version_owner(conn: sqlite3.Connection, version_id: int) -> int | None:
    row = conn.execute(
        "SELECT b.owner_id FROM bot_versions v JOIN bots b ON b.id = v.bot_id WHERE v.id = ?",
        (version_id,),
    ).fetchone()
    return row[0] if row else None


def _comparison(conn: sqlite3.Connection, comparison_id: int) -> ComparisonView:
    row = conn.execute(
        "SELECT challenger_id, incumbent_id FROM comparisons WHERE id = ?", (comparison_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(404, "no such comparison")
    c = compare.report(conn, row[0], row[1])
    low, high = c.interval()
    return ComparisonView(
        id=comparison_id, challenger=row[0], incumbent=row[1], wins=c.wins, draws=c.draws,
        losses=c.losses, pending=c.pending, score=c.score, low=low, high=high,
        p_better=c.p_better(), lost=c.lost,
    )  # fmt: skip


def app_from_env() -> FastAPI:
    return create_app(
        Path(os.environ["ARENA_DATA_DIR"]),
        GitHubOAuth(os.environ["GITHUB_CLIENT_ID"], os.environ["GITHUB_CLIENT_SECRET"]),
        os.environ["SESSION_SECRET"].encode(),
    )
