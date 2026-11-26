"""Looks for anything of the host's: files, the environment (its own and its jail's init
process'), other processes, and tries writing outside /tmp. The test plants a canary file
and environment variable on the host. Expected: plays on, finds nothing."""

import os

from arena import Bot

HOST_ONLY = [
    "/tmp/arena-canary",
    "/etc/passwd",
    "/etc/shadow",
    "/root",
    "/home",
    "/app/pyproject.toml",
    "/sys/fs/cgroup/cgroup.procs",
]
WRITES = ["/usr/escape", "/opt/escape", "/bot/escape", "/escape"]


def readable(path):
    try:
        if os.path.isdir(path):
            os.listdir(path)
        else:
            with open(path, "rb") as f:
                f.read()
        return True
    except OSError:
        return False


def writable(path):
    try:
        with open(path, "w") as f:
            f.write("x")
        return True
    except OSError:
        return False


def init_environment():
    try:
        with open("/proc/1/environ", "rb") as f:
            return f.read()
    except OSError:
        return b""


class FsProbe(Bot):
    def act(self, obs):
        if obs.turn != 0:
            return []
        for path in HOST_ONLY:
            if readable(path):
                self.log(f"ESCAPED: read {path}")
        for path in WRITES:
            if writable(path):
                self.log(f"ESCAPED: wrote {path}")
        expected = {"HOME": "/tmp", "PWD": "/tmp"}  # plus LC_CTYPE, which Python may set itself
        unexpected = {
            k: v for k, v in os.environ.items() if k != "LC_CTYPE" and expected.get(k) != v
        }
        if unexpected:
            self.log(f"ESCAPED: environment {unexpected}")
        if b"ARENA_CANARY" in init_environment():
            self.log("ESCAPED: the jail's init process carries the host environment")
        mine = {"1", str(os.getpid())}
        others = [p for p in os.listdir("/proc") if p.isdigit() and p not in mine]
        if others:
            self.log(f"ESCAPED: can see processes {others}")
        return []
