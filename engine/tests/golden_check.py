"""Replay the recorded golden games and compare state hashes.

Shared by pytest (CPython) and engine/pyodide/check_golden.mjs (Pyodide), so both runtimes
are held to the same hashes. Standard library only: it also runs inside Pyodide.
"""

import gzip
import json
from pathlib import Path

from arena_engine import ENGINE_VERSION, Rules, new_game, parse_order, state_hash, step

GOLDEN_DIR = Path(__file__).parent / "golden"
CHECKPOINT_EVERY = 25


def load(path: Path) -> dict:
    return json.loads(gzip.decompress(path.read_bytes()))


def replay_hashes(fixture: dict) -> dict[str, str]:
    """Hashes at turn 0, every CHECKPOINT_EVERY turns, and at the end."""
    state = new_game(Rules(), fixture["seed"])
    hashes = {"0": state_hash(state)}
    for turn in fixture["orders"]:
        orders = {seat: [parse_order(o) for o in turn[seat]] for seat in (0, 1)}
        state = step(state, orders).state
        if state.turn % CHECKPOINT_EVERY == 0 or state.outcome is not None:
            hashes[str(state.turn)] = state_hash(state)
    return hashes


def check(fixture: dict) -> list[str]:
    name = fixture["name"]
    if fixture["engine_version"] != ENGINE_VERSION:
        return [f"{name}: recorded for engine {fixture['engine_version']}, not {ENGINE_VERSION}"]
    actual = replay_hashes(fixture)
    if actual != fixture["hashes"]:
        diverged = sorted(
            (t for t in fixture["hashes"] if actual.get(t) != fixture["hashes"][t]), key=int
        )
        first = diverged[0] if diverged else "the end"
        return [f"{name}: diverges by turn {first}"]
    return []


def check_all(directory: Path = GOLDEN_DIR) -> tuple[int, list[str]]:
    """(number of games checked, problems found)."""
    paths = sorted(directory.glob("*.json.gz"))
    problems = [p for path in paths for p in check(load(path))]
    return len(paths), problems
