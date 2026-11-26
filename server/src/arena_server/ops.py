"""Running the live server: bootstrap, the kill switch, the budget guard, backups and restore.

    ARENA_DATA_DIR=/var/lib/arena python -m arena_server.ops <command>

systemd timers run `guard` and `backup` (deploy/systemd/); deploy/RUNBOOK.md covers the rest.
"""

import argparse
import gzip
import hashlib
import json
import logging
import os
import shutil
import sys
import tarfile
import tempfile
import time
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote

import httpx

from . import bots, metrics
from .db import connect, migrate
from .ratings import Ratings, rebuild, stored
from .settings import Settings
from .store import CODE, EGRESS_CAPPED, PAUSED, PY, REPLAY, REPLAYS, Store

log = logging.getLogger("arena.ops")
GUARD_STATE = "guard.json"
BACKUP_STATE = "backup.json"
DAY_S = 86_400


def bootstrap(data: Path) -> list[int]:
    """Migrate the database and create the built-in anchors. Safe to run on every deploy."""
    data.mkdir(parents=True, exist_ok=True)
    with closing(connect(data / "arena.db")) as conn:
        migrate(conn)
        return bots.ensure_anchors(conn)


def pause(data: Path, reason: str) -> None:
    (data / PAUSED).write_text(f"{datetime.now(UTC).isoformat()} {reason}\n")
    log.warning("ladder paused: %s", reason)


def resume(data: Path) -> None:
    (data / PAUSED).unlink(missing_ok=True)
    log.warning("ladder resumed")


# --- The budget guard ---------------------------------------------------------------------


@dataclass(frozen=True)
class Meter:
    """Outbound bytes this month, from the interface counter, less what backups uploaded:
    backups go to Cloud Storage in the VM's region, which is not billed as egress."""

    month: str  # "2026-11", UTC: the free tier's monthly allowance resets with the calendar
    used: int
    tx: int  # the interface counter at the last reading
    backup: int  # the backup upload counter at the last reading


def advance(meter: Meter | None, month: str, tx: int, backup: int) -> Meter:
    if meter is None:
        return Meter(month, 0, tx, backup)
    sent = tx - meter.tx if tx >= meter.tx else tx  # the counter restarts at boot
    used = meter.used if month == meter.month else 0
    return Meter(month, used + max(sent - (backup - meter.backup), 0), tx, backup)


def interface_tx_bytes(proc_net: Path = Path("/proc/net")) -> int:
    """Bytes sent so far by the interface that carries the default route."""
    routes = [line.split() for line in (proc_net / "route").read_text().splitlines()[1:]]
    iface = next(r[0] for r in routes if r[1] == "00000000")
    for line in (proc_net / "dev").read_text().splitlines()[2:]:
        name, counters = line.split(":", 1)
        if name.strip() == iface:
            return int(counters.split()[8])
    raise RuntimeError(f"no counters for {iface} in /proc/net/dev")


def guard(store: Store, settings: Settings, tx: int, now: datetime) -> Meter:
    """Run every few minutes. Turns the site off (Caddy answers 503) once this month's egress
    budget is spent, and back on next month; pauses the ladder if the disk fills up; expires
    old bot logs and live frame files."""
    data = store.root
    saved = _read_json(data / GUARD_STATE)
    uploaded = _read_json(data / BACKUP_STATE).get("uploaded", 0)
    meter = advance(Meter(**saved) if saved else None, now.strftime("%Y-%m"), tx, uploaded)
    _write_json(data / GUARD_STATE, asdict(meter))

    capped = data / EGRESS_CAPPED
    if meter.used >= settings.egress_month_bytes:
        if not capped.exists():
            log.warning("egress budget spent (%d bytes this month): site off", meter.used)
            capped.write_text(f"{meter.month} {meter.used}\n")
    elif capped.exists():
        log.warning("new month: site back on")
        capped.unlink()

    disk = shutil.disk_usage(data)
    if disk.used / disk.total >= settings.disk_pause_fraction and not store.paused:
        pause(data, f"disk {disk.used / disk.total:.0%} full")

    for folder, days in (("logs", settings.logs_keep_days), ("live", settings.live_keep_days)):
        if gone := expire(data / folder, days, now.timestamp()):
            log.info("expired %d files from %s", gone, folder)
    return meter


def report_alerts(store: Store, settings: Settings, url: str, client: httpx.Client) -> list[str]:
    """A dead man's switch at the uptime checker (deploy/RUNBOOK.md): a ping when all is
    well, a failure with the reasons when not. A VM that stops pinging alerts as well."""
    with closing(connect(store.root / "arena.db")) as conn:
        found = metrics.health(conn, store, settings).alerts
    if found:
        client.post(f"{url}/fail", content="\n".join(found)).raise_for_status()
    else:
        client.post(url).raise_for_status()
    return found


def expire(folder: Path, days: int, now: float) -> int:
    old = [p for p in folder.glob("*") if p.is_file() and p.stat().st_mtime < now - days * DAY_S]
    for p in old:
        p.unlink()
    return len(old)


# --- Backups ------------------------------------------------------------------------------


class Bucket(Protocol):
    def put(self, name: str, path: Path) -> None: ...
    def names(self, prefix: str) -> list[str]: ...  # sorted
    def get(self, name: str, path: Path) -> None: ...


class GCS:
    """A Cloud Storage bucket through its JSON API, signed in as the VM's service account."""

    API = "https://storage.googleapis.com"
    TOKEN = (
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
    )

    def __init__(self, bucket: str, client: httpx.Client | None = None) -> None:
        self.bucket = bucket
        self.client = client or httpx.Client(timeout=120)

    def put(self, name: str, path: Path) -> None:
        self.client.post(
            f"{self.API}/upload/storage/v1/b/{self.bucket}/o",
            params={"uploadType": "media", "name": name},
            content=path.read_bytes(),
            headers=self._auth(),
        ).raise_for_status()

    def names(self, prefix: str) -> list[str]:
        names: list[str] = []
        params = {"prefix": prefix, "fields": "items(name),nextPageToken"}
        while True:
            page = self.client.get(
                f"{self.API}/storage/v1/b/{self.bucket}/o", params=params, headers=self._auth()
            )
            body = page.raise_for_status().json()
            names += [item["name"] for item in body.get("items", [])]
            if "nextPageToken" not in body:
                return sorted(names)
            params["pageToken"] = body["nextPageToken"]

    def get(self, name: str, path: Path) -> None:
        url = f"{self.API}/storage/v1/b/{self.bucket}/o/{quote(name, safe='')}"
        with self.client.stream("GET", url, params={"alt": "media"}, headers=self._auth()) as r:
            r.raise_for_status()
            with path.open("wb") as out:
                for chunk in r.iter_bytes():
                    out.write(chunk)

    def _auth(self) -> dict[str, str]:
        token = self.client.get(self.TOKEN, headers={"Metadata-Flavor": "Google"})
        return {"Authorization": f"Bearer {token.raise_for_status().json()['access_token']}"}


def backup(data: Path, bucket: Bucket, now: datetime) -> int:
    """Upload what changed since the last run: a database snapshot (at least daily, so the
    bucket's 7-day expiry never removes the last one) and one tar of new code and replay
    files. Code and replays are content-addressed and never change, so new files are all
    there is. Returns the bytes uploaded."""
    state = {"db": "", "db_at": 0.0, "mark": 0.0, "uploaded": 0} | _read_json(data / BACKUP_STATE)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    sent = 0
    with tempfile.TemporaryDirectory(dir=data) as tmp:
        snapshot = Path(tmp) / "arena.db"
        with closing(connect(data / "arena.db")) as conn:
            conn.execute("VACUUM INTO ?", (str(snapshot),))
        digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
        if digest != state["db"] or now.timestamp() - state["db_at"] >= DAY_S:
            packed = Path(tmp) / "arena.db.gz"
            with snapshot.open("rb") as src, gzip.open(packed, "wb") as dst:
                shutil.copyfileobj(src, dst)
            bucket.put(f"db/{stamp}.db.gz", packed)
            sent += packed.stat().st_size
            state |= {"db": digest, "db_at": now.timestamp()}
        # After the snapshot, so every replay and bot the snapshot mentions is in some tar.
        mark = time.time()
        new = [
            p
            for kind, suffix in ((CODE, PY), (REPLAYS, REPLAY))
            for p in sorted((data / kind).glob(f"*/*{suffix}"))
            if p.stat().st_mtime >= state["mark"]
        ]
        if new:
            bundle = Path(tmp) / "files.tar"
            with tarfile.open(bundle, "w") as tar:
                for p in new:
                    tar.add(p, arcname=str(p.relative_to(data)))
            bucket.put(f"files/{stamp}.tar", bundle)
            sent += bundle.stat().st_size
    state |= {"mark": mark, "uploaded": state["uploaded"] + sent}
    _write_json(data / BACKUP_STATE, state)
    return sent


def restore(data: Path, bucket: Bucket) -> None:
    """A data directory rebuilt from the bucket: the newest snapshot and every file tar."""
    if (data / "arena.db").exists():
        raise SystemExit(f"{data / 'arena.db'} exists; restore only into an empty directory")
    snapshots = bucket.names("db/")
    if not snapshots:
        raise SystemExit("the bucket holds no database snapshot")
    data.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=data) as tmp:
        packed = Path(tmp) / "download"
        bucket.get(snapshots[-1], packed)
        with gzip.open(packed, "rb") as src, (data / "arena.db").open("wb") as dst:
            shutil.copyfileobj(src, dst)
        for name in bucket.names("files/"):
            bucket.get(name, packed)
            with tarfile.open(packed) as tar:
                tar.extractall(data, filter="data")
    _write_json(data / BACKUP_STATE, {"mark": time.time(), "uploaded": 0})
    log.info("restored %s and %d file bundles", snapshots[-1], len(bucket.names("files/")))


def check(data: Path, settings: Settings) -> list[str]:
    """What a restore must get right: ratings rebuild to exactly the stored table, and every
    result's replay and every uploaded version's code is on disk."""
    store, problems = Store(data), []
    with closing(connect(data / "arena.db")) as conn:
        if rebuild(conn, Ratings(settings)) != stored(conn):
            problems.append("ratings rebuilt from results differ from the stored ratings")
        for (sha,) in conn.execute("SELECT replay_sha256 FROM results"):
            if not store.path(REPLAYS, sha, REPLAY).exists():
                problems.append(f"missing replay {sha}")
        for (code,) in conn.execute("SELECT code FROM bot_versions WHERE code LIKE 'sha256:%'"):
            if not store.path(CODE, code, PY).exists():
                problems.append(f"missing bot code {code}")
    return problems


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text()) if path.exists() else {}


def _write_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value))
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(prog="arena_server.ops", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("bootstrap", help="migrate and create the built-in anchors")
    commands.add_parser("pause", help="the kill switch: stop running bots and scheduling")
    commands.choices["pause"].add_argument("reason", nargs="?", default="paused by hand")
    commands.add_parser("resume", help="undo pause")
    commands.add_parser("status", help="kill switch, egress used this month, disk")
    commands.add_parser("guard", help="egress budget, disk and expiry (a timer runs it)")
    commands.add_parser("backup", help="upload changes to ARENA_BACKUP_BUCKET (a timer runs it)")
    commands.add_parser("restore", help="rebuild an empty data directory from the bucket")
    commands.add_parser("check", help="ratings rebuild and stored files are consistent")
    args = parser.parse_args(argv)

    data = Path(os.environ["ARENA_DATA_DIR"])
    settings = Settings.load()
    match args.command:
        case "bootstrap":
            log.info("anchors: %s", bootstrap(data))
        case "pause":
            pause(data, args.reason)
        case "resume":
            resume(data)
        case "status":
            meter = _read_json(data / GUARD_STATE)
            disk = shutil.disk_usage(data)
            paused = (data / PAUSED).read_text().strip() if Store(data).paused else "no"
            log.info("paused: %s", paused)
            log.info("site off for egress: %s", (data / EGRESS_CAPPED).exists())
            used, cap = meter.get("used", 0), settings.egress_month_bytes
            log.info("egress this month: %d of %d bytes", used, cap)
            log.info("disk: %.0f%% used", 100 * disk.used / disk.total)
        case "guard":
            guard(Store(data), settings, interface_tx_bytes(), datetime.now(UTC))
            if url := os.environ.get("ARENA_HEALTHCHECK_URL"):
                with httpx.Client(timeout=30) as client:
                    for alert in report_alerts(Store(data), settings, url, client):
                        log.warning("alert: %s", alert)
        case "backup":
            sent = backup(data, GCS(os.environ["ARENA_BACKUP_BUCKET"]), datetime.now(UTC))
            log.info("backup uploaded %d bytes", sent)
        case "restore":
            restore(data, GCS(os.environ["ARENA_BACKUP_BUCKET"]))
        case "check":
            problems = check(data, settings)
            for p in problems:
                log.error("%s", p)
            log.info("check: %s", f"{len(problems)} problems" if problems else "ok")
            return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
