"""The exported boss against every scripted baseline, through the CLI runner.

    uv run --project rl python -m arena_rl.evaluate rl/runs/v1/boss.py 200

The boss runs as its shipped file in its own harness process, exactly as a local match runs
it. Seed pairs: each seed is played from both seats, and seeds 1000..1000+N-1 never occur in
training (train.TRAIN_SEEDS). They start at 1000 because seeds 0..19 are the in-training
evaluation's, and design choices were made while watching those. Scores count a draw as
half a win, with a 95% Wilson interval.
"""

import json
import sys
from concurrent.futures import ProcessPoolExecutor

from arena.tournament import Game, play, standing

from .train import TRAIN_SEEDS

BASELINES = ("random", "greedy", "rush", "turtle", "scout")
FIRST_SEED = 1000


def evaluate(bot: str, seed_pairs: int, jobs: int) -> dict[str, dict[str, float | int]]:
    assert FIRST_SEED + seed_pairs <= TRAIN_SEEDS[0]
    work = [
        (bot, f"builtin:{b}", seed, seat)
        for b in BASELINES
        for seed in range(FIRST_SEED, FIRST_SEED + seed_pairs)
        for seat in (0, 1)
    ]
    with ProcessPoolExecutor(jobs) as pool:
        games: list[Game] = list(pool.map(play, work, chunksize=4))
    report: dict[str, dict[str, float | int]] = {}
    for b in BASELINES:
        s = standing(games, bot, f"builtin:{b}")
        lo, hi = s.interval()
        report[b] = {"wins": s.wins, "draws": s.draws, "losses": s.losses,
                     "score": s.score, "lo": lo, "hi": hi}  # fmt: skip
    return report


def main() -> None:
    bot, seed_pairs = sys.argv[1], int(sys.argv[2])
    jobs = int(sys.argv[3]) if len(sys.argv) > 3 else 8
    sys.stdout.write(json.dumps(evaluate(bot, seed_pairs, jobs), indent=2) + "\n")


if __name__ == "__main__":
    main()
