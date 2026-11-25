"""Rules from CLAUDE.md that are enforced by checks rather than by memory."""

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENGINE_SRC = ROOT / "engine" / "src"
ENGINE_PROBE = "engine/src/arena_engine/_probe.py"
SERVER_PROBE = "server/src/arena_server/_probe.py"

# ruff's banned-api can't see builtins, so these are checked on the AST instead.
NONDETERMINISTIC_BUILTINS = {
    "hash": "hash() of str changes with PYTHONHASHSEED",
    "id": "id() is a memory address and differs between runs",
    "open": "no I/O in the engine",
    "input": "no I/O in the engine",
}


def forbidden_builtin_calls(source: str) -> list[str]:
    return [
        f"line {node.lineno}: {node.func.id}() - {NONDETERMINISTIC_BUILTINS[node.func.id]}"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in NONDETERMINISTIC_BUILTINS
    ]


def ruff_check(source: str, as_path: str) -> subprocess.CompletedProcess[str]:
    """Lint `source` as if it lived at `as_path`, so that directory's config applies."""
    return subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--no-cache", "--stdin-filename", as_path, "-"],
        input=source,
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )


def test_engine_has_no_runtime_dependencies() -> None:
    project = tomllib.loads((ROOT / "engine" / "pyproject.toml").read_text())["project"]
    assert project["dependencies"] == []


@pytest.mark.parametrize(
    "source",
    [
        "import time\n\ntime.monotonic()\n",
        "from datetime import datetime\n\ndatetime.now()\n",
        "import os\n\nos.environ.get('X')\n",
        "import random\n\nrandom.random()\n",
        "from random import shuffle\n\nshuffle([1, 2])\n",
        "import threading\n\nthreading.Thread()\n",
        "import uuid\n\nuuid.uuid4()\n",
    ],
)
def test_engine_rejects_impure_code(source: str) -> None:
    result = ruff_check(source, ENGINE_PROBE)
    assert result.returncode == 1
    assert "TID251" in result.stdout, result.stdout


@pytest.mark.parametrize("call", ["hash('crystal')", "id(unit)", "open('state.json')", "input()"])
def test_builtin_scan_catches_nondeterministic_calls(call: str) -> None:
    assert forbidden_builtin_calls(f"x = {call}\n")


def test_engine_source_has_no_nondeterministic_builtins() -> None:
    offenders = {
        str(path.relative_to(ROOT)): found
        for path in ENGINE_SRC.rglob("*.py")
        if (found := forbidden_builtin_calls(path.read_text()))
    }
    assert offenders == {}


def test_engine_rejects_print() -> None:
    result = ruff_check("print('debug')\n", ENGINE_PROBE)
    assert "T201" in result.stdout, result.stdout


def test_engine_allows_a_seeded_rng() -> None:
    result = ruff_check("from random import Random\n\nRNG = Random(7)\n", ENGINE_PROBE)
    assert result.returncode == 0, result.stdout


def test_purity_bans_are_scoped_to_the_engine() -> None:
    result = ruff_check("import time\n\ntime.monotonic()\n", SERVER_PROBE)
    assert result.returncode == 0, result.stdout
