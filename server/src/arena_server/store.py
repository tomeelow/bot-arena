"""Content-addressed files: bot code and replays, named by their sha256.

The host never interprets bot code: it only stores the bytes and hands the path to a jail.
"""

import hashlib
import os
from pathlib import Path


class Store:
    def __init__(self, root: Path) -> None:
        self.root = root

    def put(self, kind: str, data: bytes, suffix: str) -> str:
        """Write `data` once, atomically. Returns "sha256:<hex>"."""
        digest = hashlib.sha256(data).hexdigest()
        path = self._path(kind, digest, suffix)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return f"sha256:{digest}"

    def path(self, kind: str, ref: str, suffix: str) -> Path:
        return self._path(kind, ref.removeprefix("sha256:"), suffix)

    def _path(self, kind: str, digest: str, suffix: str) -> Path:
        return self.root / kind / digest[:2] / f"{digest}{suffix}"


CODE, REPLAYS = "code", "replays"
PY, REPLAY = ".py", ".json.gz"
