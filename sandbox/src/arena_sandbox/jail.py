"""Ranked bots run here: CPython in bubblewrap, one fresh jail and one cgroup per bot per
match (ADR-002). The runner still parses everything a jailed bot says as hostile input.

The host this runs on must provide (the sandbox image does, see sandbox/entrypoint.sh):
  ARENA_CGROUP_ROOT  a cgroup v2 directory we may create children in, with the cpu, memory
                     and pids controllers enabled for them
  ARENA_VENV         a read-only virtualenv with arena and arena_engine installed
  ARENA_SECCOMP      the BPF compiled from sandbox/seccomp_policy.py
"""

import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arena.limits import Limits
from arena.runner import Channel, Failure, MatchRecord, ProcessChannel, Reply, run_match
from arena_engine import Rules

NOBODY = "65534"
BOT_PATH = "/bot/main.py"
CPU_PERIOD_US = 100_000
CLEANUP_TIMEOUT_S = 5.0
# Joins the bot's cgroup before exec, so even code that runs on import is contained, and
# hands bubblewrap the seccomp program on fd 3.
ENTER = 'cg=$1; bpf=$2; shift 2; echo $$ > "$cg/cgroup.procs" && exec "$@" 3<"$bpf"'


@dataclass(frozen=True)
class JailConfig:
    cgroup_root: Path
    venv: Path
    seccomp: Path
    bwrap: str = shutil.which("bwrap") or "/usr/bin/bwrap"

    @classmethod
    def from_env(cls) -> JailConfig:
        return cls(
            cgroup_root=Path(os.environ["ARENA_CGROUP_ROOT"]),
            venv=Path(os.environ["ARENA_VENV"]),
            seccomp=Path(os.environ["ARENA_SECCOMP"]),
        )


def bwrap_argv(spec: str, config: JailConfig, limits: Limits) -> list[str]:
    """Everything a bot gets: read-only system and arena files, its own code, a small /tmp.
    No network, no other processes, no environment, no capabilities."""
    argv = [
        config.bwrap,
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--uid", NOBODY,
        "--gid", NOBODY,
        "--cap-drop", "ALL",
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--symlink", "usr/bin", "/bin",
        "--ro-bind", str(config.venv), str(config.venv),
        "--proc", "/proc",
        "--dev", "/dev",
        "--size", str(limits.tmp_mb * 2**20), "--tmpfs", "/tmp",
        "--setenv", "HOME", "/tmp",
        "--chdir", "/tmp",
        "--seccomp", "3",
    ]  # fmt: skip
    if not spec.startswith("builtin:"):
        argv += ["--ro-bind", spec, BOT_PATH]
        spec = BOT_PATH
    argv += ["--remount-ro", "/"]  # last: everything but /tmp ends up read-only
    return [*argv, str(config.venv / "bin" / "python"), "-I", "-B", "-m", "arena.harness", spec]


class JailChannel:
    """A bot in its own jail and cgroup. Thinking time is CPU time from the cgroup, measured
    from one reply to the next, so work done by background threads between turns counts."""

    def __init__(self, spec: str, config: JailConfig, limits: Limits) -> None:
        self.cgroup = config.cgroup_root / f"bot-{uuid.uuid4().hex}"
        self.cgroup.mkdir()
        self.memory_mb = limits.memory_mb
        for name, value in {
            "memory.max": str(limits.memory_mb * 2**20),
            "memory.swap.max": "0",
            "pids.max": str(limits.max_tasks),
            "cpu.max": f"{CPU_PERIOD_US} {CPU_PERIOD_US}",  # one core
        }.items():
            (self.cgroup / name).write_text(value)
        argv = ["/bin/sh", "-c", ENTER, "sh", str(self.cgroup), str(config.seccomp)]
        # An empty environment for the whole chain: bubblewrap's own init process stays
        # visible in /proc/1/environ inside the jail, so it must carry nothing of the host's.
        self.process = ProcessChannel(
            argv + bwrap_argv(spec, config, limits), limits.reply_max_bytes, env={}
        )
        self.cpu_us = 0

    def send(self, message: dict[str, Any]) -> None:
        self.process.send(message)

    def receive(self, timeout_s: float) -> Reply:
        reply = self.process.receive(timeout_s)
        if reply.line is None:
            if reply.problem is Failure.CRASH and self._oom_killed():
                return Reply(None, reply.ms, Failure.MEMORY, f"used more than {self.memory_mb} MiB")
            return reply
        used = self._cpu_usage_us()
        ms = (used - self.cpu_us) / 1000
        self.cpu_us = used
        return Reply(reply.line, ms)

    def close(self) -> str:
        (self.cgroup / "cgroup.kill").write_text("1")
        stderr = self.process.close()
        deadline = time.monotonic() + CLEANUP_TIMEOUT_S
        while (self.cgroup / "cgroup.procs").read_text().strip():
            if time.monotonic() > deadline:
                raise RuntimeError(f"processes survived cgroup.kill in {self.cgroup}")
            time.sleep(0.01)
        self.cgroup.rmdir()
        return stderr

    def _cpu_usage_us(self) -> int:
        for line in (self.cgroup / "cpu.stat").read_text().splitlines():
            key, value = line.split()
            if key == "usage_usec":
                return int(value)
        raise RuntimeError("cpu.stat has no usage_usec")

    def _oom_killed(self) -> bool:
        events = dict(
            line.split() for line in (self.cgroup / "memory.events").read_text().splitlines()
        )
        return int(events.get("oom_kill", "0")) > 0


def ranked_match(
    players: tuple[str, str],
    seed: int,
    config: JailConfig | None = None,
    rules: Rules | None = None,
    limits: Limits | None = None,
) -> MatchRecord:
    """A match with both bots jailed and every limit enforced. An exception out of here is a
    platform failure: the caller voids the match instead of rating it."""
    jail = config or JailConfig.from_env()

    def opener(spec: str, limits: Limits) -> Channel:
        return JailChannel(spec, jail, limits)

    return run_match(players, seed, rules, limits, opener=opener, enforce=True)
