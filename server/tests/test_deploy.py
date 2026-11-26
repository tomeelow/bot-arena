"""The deploy files keep the rules the code relies on (deploy/check-caddy.sh runs Caddy itself)."""

import importlib
import re
import shlex
from pathlib import Path

import pytest
from arena_server import ops

DEPLOY = Path(__file__).parents[2] / "deploy"
UNITS = sorted((DEPLOY / "systemd").glob("arena-*.service"))


def directives(unit: Path, key: str) -> list[str]:
    return [
        line.split("=", 1)[1]
        for line in unit.read_text().splitlines()
        if line.startswith(f"{key}=")
    ]


def test_the_worker_unit_carries_no_secrets():
    """bubblewrap's init shows the worker's environment to every jail at /proc/1/environ."""
    worker = DEPLOY / "systemd" / "arena-worker@.service"
    assert directives(worker, "EnvironmentFile") == []
    env = [pair for line in directives(worker, "Environment") for pair in line.split()]
    names = {pair.split("=")[0] for pair in env}
    assert names <= {"ARENA_DATA_DIR", "ARENA_VENV", "ARENA_SECCOMP"}


def test_every_unit_starts_something_that_exists():
    for unit in UNITS:
        (start,) = directives(unit, "ExecStart")
        argv = shlex.split(start)
        if "-m" in argv:
            module = argv[argv.index("-m") + 1]
            importlib.import_module(module)
            if module == "arena_server.ops":
                with pytest.raises(SystemExit) as help:
                    ops.main([argv[argv.index("-m") + 2], "--help"])
                assert help.value.code == 0, unit.name
        elif argv[0].endswith("uvicorn"):
            module, attr = argv[argv.index("--factory") + 1].split(":")
            assert callable(getattr(importlib.import_module(module), attr))


def test_caddy_proxies_to_the_port_the_api_listens_on():
    (start,) = directives(DEPLOY / "systemd" / "arena-api.service", "ExecStart")
    port = shlex.split(start)[shlex.split(start).index("--port") + 1]
    upstreams = re.findall(r"reverse_proxy (\S+)", (DEPLOY / "Caddyfile").read_text())
    assert upstreams and set(upstreams) == {f"127.0.0.1:{port}"}
