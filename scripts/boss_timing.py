"""The boss's per-turn CPU time in the ranked jail, as the host measures it (Phase 11).

    docker build -f sandbox/Dockerfile -t arena-sandbox .
    docker run --rm --privileged -v "$PWD/rl/runs/v1:/boss:ro" -v "$PWD/scripts:/scripts:ro" \
        arena-sandbox python /scripts/boss_timing.py /boss/boss.py 4

Plays the bundle against every built-in bot from both seats, with every ranked limit
enforced, and reports the percentiles of its think time against the turn budget.
"""

import json
import math
import sys

from arena.limits import Limits
from arena_sandbox import ranked_match

BASELINES = ("random", "greedy", "rush", "turtle", "scout")


def main() -> None:
    bot, seeds = sys.argv[1], int(sys.argv[2])
    times: list[int] = []
    results: list[str] = []
    for baseline in BASELINES:
        for seed in range(seeds):
            for seat in (0, 1):
                players = (bot, f"builtin:{baseline}")[:: 1 if seat == 0 else -1]
                record = ranked_match((players[0], players[1]), seed)
                times += [t[seat] for t in record.think_ms]
                outcome = "won" if record.result.winner == seat else "did not win"
                results.append(f"{baseline} {seed}/{seat}: {outcome}, {record.result.reason}")
    ordered = sorted(times)

    def pct(q: float) -> int:
        return ordered[math.ceil(q * len(ordered)) - 1]

    report = {
        "turns": len(ordered),
        "p50_ms": pct(0.5),
        "p99_ms": pct(0.99),
        "max_ms": ordered[-1],
        "turn_budget_ms": Limits.load().turn_ms,
        "results": results,
    }
    sys.stdout.write(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
