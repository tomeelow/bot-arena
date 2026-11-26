"""Running the live server: the kill switch, the budget caps, backups and a restore drill."""

import json
import os
import shutil
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from random import Random
from types import SimpleNamespace

import httpx
import plays
import pytest
from arena_server import bots, ladder, ops, scheduler
from arena_server.db import connect
from arena_server.ratings import Ratings, stored
from arena_server.settings import Settings
from arena_server.store import EGRESS_CAPPED, Store
from arena_server.worker import Worker

SETTINGS = Settings.load()
RATINGS = Ratings(SETTINGS)
NOV, DEC = datetime(2026, 11, 30, tzinfo=UTC), datetime(2026, 12, 1, tzinfo=UTC)


@pytest.fixture
def data(tmp_path):
    ops.bootstrap(tmp_path / "data")
    return tmp_path / "data"


def ladder_with_two_owners(conn, store: Store) -> int:
    owner = bots.ensure_user(conn, "ada", github_id=1)
    code = b"from arena.builtin.rush import RushBot as R\n\nclass Mine(R):\n    pass\n"
    return bots.submit_version(conn, store, bots.create_bot(conn, owner, "mine"), code)


def queued(conn) -> list[int]:
    return [r[0] for r in conn.execute("SELECT id FROM matches WHERE status = 'queued'")]


def test_bootstrap_creates_the_anchors_once(data):
    first = ops.bootstrap(data)
    assert ops.bootstrap(data) == first and len(first) == len(bots.ANCHORS)


def test_the_kill_switch_stops_bots_and_scheduling_and_loses_nothing(data):
    conn, store = connect(data / "arena.db"), Store(data)
    ladder_with_two_owners(conn, store)
    worker = Worker(conn, store, plays.quick)
    assert worker.step()  # validation: the version goes active and placements are queued
    waiting = queued(conn)
    assert waiting

    ops.pause(data, "test")
    assert not worker.step()
    scheduler.tick(conn, store, RATINGS, SETTINGS, Random(1))
    assert queued(conn) == waiting  # nothing played, nothing added, nothing dropped

    ops.resume(data)
    assert worker.step()
    assert len(queued(conn)) == len(waiting) - 1


def test_the_scheduler_stops_for_the_day_at_the_match_cap(db, store):
    for name in bots.ANCHORS:
        bots.builtin_version(db, name)
    bots.activate(db, ladder_with_two_owners(db, store))
    capped = replace(SETTINGS, matches_per_day=3, queue_target=100)
    ladder.top_up(db, RATINGS, capped, Random(2))
    assert len(queued(db)) == 4  # a pairing is queued from both seats, so it can end on cap + 1
    assert ladder.top_up(db, RATINGS, capped, Random(2)) == []
    db.execute("UPDATE matches SET created_at = datetime('now', '-25 hours')")
    assert ladder.top_up(db, RATINGS, capped, Random(2))


def test_the_egress_meter_survives_reboots_months_and_backups():
    m = ops.advance(None, "2026-11", tx=5_000, backup=0)
    assert m.used == 0  # bytes before the first reading are not ours to count
    m = ops.advance(m, "2026-11", tx=8_000, backup=1_000)
    assert m.used == 2_000  # 3,000 sent, 1,000 of them backups to Cloud Storage
    m = ops.advance(m, "2026-11", tx=700, backup=1_000)
    assert m.used == 2_700  # the counter restarted at boot
    m = ops.advance(m, "2026-12", tx=1_000, backup=1_000)
    assert (m.month, m.used) == ("2026-12", 300)


def test_tx_bytes_come_from_the_default_route_interface(tmp_path):
    (tmp_path / "route").write_text(
        "Iface\tDestination\tGateway\ndocker0\t0011A8C0\t00000000\nens4\t00000000\t0100800A\n"
    )
    (tmp_path / "dev").write_text(
        "Inter-|   Receive  |  Transmit\n"
        " face |bytes packets errs drop fifo frame compressed multicast|bytes packets\n"
        "    lo: 10 1 0 0 0 0 0 0 10 1 0 0 0 0 0 0\n"
        "  ens4: 999 9 0 0 0 0 0 0 123456 77 0 0 0 0 0 0\n"
    )
    assert ops.interface_tx_bytes(tmp_path) == 123456


def test_the_guard_turns_the_site_off_when_the_budget_is_spent_and_on_next_month(data):
    store, budget = Store(data), replace(SETTINGS, egress_month_bytes=1_000)
    ops.guard(store, budget, tx=0, now=NOV)
    ops.guard(store, budget, tx=999, now=NOV)
    assert not (data / EGRESS_CAPPED).exists()
    ops.guard(store, budget, tx=1_000, now=NOV)
    assert (data / EGRESS_CAPPED).exists()
    ops.guard(store, budget, tx=1_100, now=DEC)
    assert not (data / EGRESS_CAPPED).exists()


def test_the_guard_pauses_the_ladder_when_the_disk_fills(data, monkeypatch):
    full = SimpleNamespace(total=100, used=90, free=10)
    monkeypatch.setattr(shutil, "disk_usage", lambda _: full)
    ops.guard(Store(data), SETTINGS, tx=0, now=NOV)
    assert Store(data).paused


def test_the_guard_expires_old_logs_and_live_frames_only(data):
    now = time.time()
    for folder, days in (("logs", SETTINGS.logs_keep_days), ("live", SETTINGS.live_keep_days)):
        (data / folder).mkdir()
        old, fresh = data / folder / "1.json", data / folder / "2.json"
        old.write_text("{}")
        fresh.write_text("{}")
        stale = now - (days + 1) * ops.DAY_S
        os.utime(old, (stale, stale))
    ops.guard(Store(data), SETTINGS, tx=0, now=datetime.fromtimestamp(now, UTC))
    assert sorted(p.name for p in (data / "logs").iterdir()) == ["2.json"]
    assert sorted(p.name for p in (data / "live").iterdir()) == ["2.json"]


class FolderBucket:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.puts: list[str] = []

    def put(self, name: str, path: Path) -> None:
        self.puts.append(name)
        (self.root / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, self.root / name)

    def names(self, prefix: str) -> list[str]:
        return sorted(str(p.relative_to(self.root)) for p in self.root.glob(f"{prefix}*"))

    def get(self, name: str, path: Path) -> None:
        shutil.copyfile(self.root / name, path)


def test_a_restore_from_backups_rebuilds_the_same_ladder(data, tmp_path):
    """The Phase 9 restore drill, end to end on a small ladder."""
    conn, store = connect(data / "arena.db"), Store(data)
    ladder_with_two_owners(conn, store)
    worker = Worker(conn, store, plays.quick)
    bucket = FolderBucket(tmp_path / "bucket")

    for _ in range(3):
        worker.step()
    assert ops.backup(data, bucket, NOV) > 0
    while worker.step():
        pass
    ops.backup(data, bucket, NOV.replace(hour=1))
    assert ops.backup(data, bucket, NOV.replace(hour=2)) == 0  # nothing changed

    fresh = tmp_path / "fresh"
    ops.restore(fresh, bucket)
    assert ops.check(fresh, SETTINGS) == []
    restored = connect(fresh / "arena.db")
    assert stored(restored) == stored(conn) and stored(conn)
    with pytest.raises(SystemExit):
        ops.restore(fresh, bucket)  # never over a live database


def test_check_finds_a_missing_replay(data):
    conn, store = connect(data / "arena.db"), Store(data)
    ladder_with_two_owners(conn, store)
    worker = Worker(conn, store, plays.quick)
    worker.step()
    worker.step()
    for replay in (data / "replays").glob("*/*"):
        replay.unlink()
    assert any("missing replay" in p for p in ops.check(data, SETTINGS))


def test_gcs_signs_in_with_the_vm_token_and_pages_through_listings(tmp_path):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "metadata.google.internal":
            assert request.headers["metadata-flavor"] == "Google"
            return httpx.Response(200, json={"access_token": "t"})
        assert request.headers["authorization"] == "Bearer t"
        if request.url.path.startswith("/upload/"):
            return httpx.Response(200, json={})
        if request.url.params.get("alt") == "media":
            return httpx.Response(200, content=b"bytes")
        if request.url.params.get("pageToken") == "2":
            return httpx.Response(200, json={"items": [{"name": "db/a"}]})
        return httpx.Response(200, json={"items": [{"name": "db/b"}], "nextPageToken": "2"})

    bucket = ops.GCS("arena-backups", httpx.Client(transport=httpx.MockTransport(handler)))
    (tmp_path / "f").write_bytes(b"up")
    bucket.put("db/x.db.gz", tmp_path / "f")
    assert bucket.names("db/") == ["db/a", "db/b"]
    bucket.get("files/2026 a.tar", tmp_path / "g")
    assert (tmp_path / "g").read_bytes() == b"bytes"
    upload = next(r for r in seen if r.url.path.startswith("/upload/"))
    assert (upload.url.params["name"], upload.content) == ("db/x.db.gz", b"up")
    assert any(r.url.raw_path.endswith(b"/o/files%2F2026%20a.tar?alt=media") for r in seen)


def test_status_and_check_run_from_the_command_line(data, monkeypatch):
    monkeypatch.setenv("ARENA_DATA_DIR", str(data))
    (data / ops.GUARD_STATE).write_text(json.dumps({"used": 5}))
    assert ops.main(["status"]) == 0
    assert ops.main(["check"]) == 0


def test_the_boss_is_uploaded_as_an_ordinary_pending_version(data):
    code = b"from arena.builtin.scout import ScoutBot as S\n\nclass Boss(S):\n    pass\n"
    first = ops.upload_boss(data, SETTINGS, code)
    second = ops.upload_boss(data, SETTINGS, code + b"\n")
    with pytest.raises(ValueError, match="bytes"):
        ops.upload_boss(data, SETTINGS, b"x" * (SETTINGS.upload_max_bytes + 1))
    conn = connect(data / "arena.db")
    rows = conn.execute(
        """SELECT v.id, v.n, v.status, b.name, u.handle, u.github_id FROM bot_versions v
           JOIN bots b ON b.id = v.bot_id JOIN users u ON u.id = b.owner_id
           WHERE v.id IN (?, ?) ORDER BY v.id""",
        (first, second),
    ).fetchall()
    assert [tuple(r) for r in rows] == [
        (first, 1, "pending", "boss", "arena-boss", None),
        (second, 2, "pending", "boss", "arena-boss", None),
    ]
    # From here the worker treats it like anyone's upload: a smoke match, then placement.
    Worker(conn, Store(data), plays.quick).step()
    status = conn.execute("SELECT status FROM bot_versions WHERE id = ?", (first,)).fetchone()
    assert status[0] == "active"
    assert queued(conn)
