"""Engine speed on the golden games: step() and observe() only, no bot time.

    uv run python engine/tests/bench_engine.py

Record results in docs/benchmarks.md. Not a gate: Phase 11 decides whether RL needs more.
"""

import logging
import platform
import sys
import time
from statistics import mean

from golden_check import GOLDEN_DIR, load

from arena_engine import Rules, new_game, observe, parse_order, step

log = logging.getLogger(__name__)
ROUNDS = 5


def main() -> None:
    games = [load(p) for p in sorted(GOLDEN_DIR.glob("*.json.gz"))]
    streams = [
        (g["seed"], [{s: [parse_order(o) for o in t[s]] for s in (0, 1)} for t in g["orders"]])
        for g in games
    ]

    start = time.perf_counter()
    for seed in range(200):
        new_game(Rules(), seed)
    mapgen_ms = (time.perf_counter() - start) / 200 * 1000

    step_s, observe_s, turns, units = 0.0, 0.0, 0, []
    for _ in range(ROUNDS):
        for seed, orders in streams:
            state = new_game(Rules(), seed)
            for turn_orders in orders:
                t0 = time.perf_counter()
                state = step(state, turn_orders).state
                t1 = time.perf_counter()
                observe(state, 0)
                observe(state, 1)
                observe_s += time.perf_counter() - t1
                step_s += t1 - t0
                turns += 1
                units.append(len(state.units))

    log.info("Python %s on %s (%s)", sys.version.split()[0], platform.machine(), platform.system())
    log.info("turns timed: %d, mean units on the board: %.1f", turns, mean(units))
    log.info("new_game: %.2f ms", mapgen_ms)
    log.info("step:     %.3f ms/turn  (%.0f turns/s)", step_s / turns * 1000, turns / step_s)
    log.info("observe:  %.3f ms/call", observe_s / (2 * turns) * 1000)
    log.info("step + both observes: %.0f turns/s", turns / (step_s + observe_s))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
