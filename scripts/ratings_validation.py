"""Validate the rating system on a synthetic ladder whose true order is known, and write
docs/ratings_validation.md.

    uv run python scripts/ratings_validation.py

Population: the built-in bots at several noise levels (`builtin:NAME~EPS` replaces each
order with a random one with probability EPS), plus random. Ground truth: a long round robin,
every map from both seats, fitted with Bradley-Terry. Then the real ladder (matchmaker,
workers, live ratings) plays, and its view is checked against the truth.

The targets below were fixed before the first run. A miss is reported, not tuned away.
"""

import argparse
import logging
import math
import os
import statistics
import tempfile
from datetime import date
from itertools import combinations, pairwise
from pathlib import Path
from random import Random

from arena.runner import MatchRecord, run_match
from arena.tournament import Game, round_robin
from arena_engine import Rules
from arena_server import ladder
from arena_server.bots import create_bot, ensure_user
from arena_server.db import connect, migrate
from arena_server.queue import immediate
from arena_server.ratings import Rating, Ratings, rated_results, stored
from arena_server.settings import Settings
from arena_server.store import Store
from arena_server.worker import Worker

log = logging.getLogger("validation")
OUT = Path(__file__).resolve().parent.parent / "docs" / "ratings_validation.md"
POPULATION = ["builtin:random"] + [
    f"builtin:{name}~{eps}" if eps else f"builtin:{name}"
    for name in ("greedy", "rush", "turtle", "scout")
    for eps in (0, 0.25, 0.5, 0.75)
]
CHECKPOINTS = (10, 20, 30, 40, 50, 60)

# Fixed before the first run.
TARGET_TAU_AT_50 = 0.90  # Kendall tau between the ladder's order and the true order
TARGET_CALIBRATION = 0.10  # |observed - predicted| win rate, per bin with >= 30 games
TARGET_STRONGER = 0.15  # |truly stronger - claimed|, per bin with >= 10 pairs
TARGET_CONVERGENCE = 50  # median rated games until sigma < provisional_sigma


def bradley_terry(games: list[Game], bots: list[str]) -> dict[str, float]:
    """Strengths by the minorise-maximise algorithm. Each pair gets one virtual draw, so a
    bot that never wins still gets a finite (tiny) strength."""
    wins = {(a, b): 0.5 for a in bots for b in bots if a != b}
    played = {(a, b): 1.0 for a in bots for b in bots if a != b}
    for g in games:
        wins[(g.a, g.b)] += g.score(g.a)
        wins[(g.b, g.a)] += g.score(g.b)
        played[(g.a, g.b)] += 1
        played[(g.b, g.a)] += 1
    strength = dict.fromkeys(bots, 1.0)
    for _ in range(2000):
        new = {
            a: sum(wins[(a, b)] for b in bots if b != a)
            / sum(played[(a, b)] / (strength[a] + strength[b]) for b in bots if b != a)
            for a in bots
        }
        total = sum(new.values())
        strength = {a: s * len(bots) / total for a, s in new.items()}
    return strength


def kendall_tau(pairs: list[tuple[float, float]]) -> float:
    """Over (predicted, true) scores: concordant minus discordant, over all pairs."""
    concordant = discordant = 0
    for (p1, t1), (p2, t2) in combinations(pairs, 2):
        sign = (p1 - p2) * (t1 - t2)
        concordant += sign > 0
        discordant += sign < 0
    total = len(pairs) * (len(pairs) - 1) / 2
    return (concordant - discordant) / total


def bins(
    points: list[tuple[float, float]], edges: list[float]
) -> list[tuple[str, int, float, float]]:
    """(label, count, mean predicted, mean observed) for each bin of predictions."""
    rows = []
    for lo, hi in pairwise(edges):
        inside = [(p, o) for p, o in points if lo <= p < hi or (hi == edges[-1] and p == hi)]
        if inside:
            rows.append(
                (
                    f"{lo:.1f}-{hi:.1f}",
                    len(inside),
                    statistics.fmean(p for p, _ in inside),
                    statistics.fmean(o for _, o in inside),
                )
            )
    return rows


def play_local(players: tuple[str, str], seed: int, rules: Rules | None) -> MatchRecord:
    return run_match(players, seed, rules)


def run_ladder(settings: Settings, ratings: Ratings, rng: Random, tmp: Path):
    """The real ladder: matchmaker, worker and live ratings, one owner per bot."""
    conn = connect(tmp / "arena.db")
    migrate(conn)
    versions: dict[int, str] = {}
    for i, spec in enumerate(POPULATION):
        owner = ensure_user(conn, f"owner{i}", github_id=i + 1)
        bot = create_bot(conn, owner, spec)
        with immediate(conn):
            vid = conn.execute(
                "INSERT INTO bot_versions (bot_id, n, code, status) "
                "VALUES (?, 1, ?, 'active') RETURNING id",
                (bot, spec),
            ).fetchone()[0]
        versions[vid] = spec
    worker = Worker(conn, Store(tmp / "data"), play_local, settings, rng=rng)
    snapshots: dict[int, dict[int, Rating]] = {}
    checkpoints = list(CHECKPOINTS)
    while checkpoints:
        ladder.top_up(conn, ratings, settings, rng)
        if not worker.step():
            break
        table = stored(conn)
        mean_games = sum(r.games for r in table.values()) / len(versions)
        if mean_games >= checkpoints[0]:
            snapshots[checkpoints.pop(0)] = table
            log.info("ladder: %d games per bot", max(snapshots))
    return conn, versions, snapshots


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--truth-seed-pairs", type=int, default=10)
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1)
    parser.add_argument("--seed", type=int, default=2026, help="different seeds, different run")
    args = parser.parse_args()
    settings = Settings.load()
    ratings = Ratings(settings)

    log.info("ground truth: round robin of %d bots", len(POPULATION))
    truth_games = round_robin(
        POPULATION, args.truth_seed_pairs, args.jobs, first_seed=10**6 + 1000 * args.seed
    )
    strength = bradley_terry(truth_games, POPULATION)

    with tempfile.TemporaryDirectory() as tmp:
        conn, versions, snapshots = run_ladder(settings, ratings, Random(args.seed), Path(tmp))

        def tau(table: dict[int, Rating]) -> float:
            return kendall_tau([(table[v].mu, strength[spec]) for v, spec in versions.items()])

        taus = {n: tau(t) for n, t in snapshots.items()}

        # Calibration of p_win, prequentially: each game predicted from the ratings before it.
        current: dict[int, Rating] = {}
        predictions: list[tuple[float, float]] = []
        settle: dict[int, int] = {}
        for row in rated_results(conn):
            a = current.get(row["v0"], ratings.prior())
            b = current.get(row["v1"], ratings.prior())
            outcome = 0.5 if row["winner_seat"] is None else float(row["winner_seat"] == 0)
            predictions.append((ratings.p_win(a, b), outcome))
            current[row["v0"]], current[row["v1"]] = ratings.update(a, b, row["winner_seat"])
            for v in (row["v0"], row["v1"]):
                if v not in settle and current[v].sigma < settings.provisional_sigma:
                    settle[v] = current[v].games
        final = stored(conn)

    brier = statistics.fmean((p - o) ** 2 for p, o in predictions)
    log_loss = -statistics.fmean(
        o * math.log(max(p, 1e-9)) + (1 - o) * math.log(max(1 - p, 1e-9)) for p, o in predictions
    )
    calibration = bins(predictions, [i / 10 for i in range(11)])

    claims: list[tuple[float, float]] = []
    for (va, sa), (vb, sb) in combinations(versions.items(), 2):
        p = ratings.p_stronger(final[va], final[vb])
        truly = float(strength[sa] > strength[sb])
        claims.append((p, truly) if p >= 0.5 else (1 - p, 1 - truly))
    stronger = bins(claims, [0.5, 0.6, 0.7, 0.8, 0.9, 1.0])

    settled = sorted(settle.values())
    median_settle = statistics.median(settled) if len(settled) == len(versions) else math.inf

    checks = [
        ("Kendall tau at 50 games per bot", f"{taus[50]:.3f}", f">= {TARGET_TAU_AT_50}",
         taus[50] >= TARGET_TAU_AT_50),
        ("Worst p_win calibration gap (bins with >= 30 games)",
         f"{max((abs(o - p) for _, n, p, o in calibration if n >= 30), default=0):.3f}",
         f"<= {TARGET_CALIBRATION}",
         all(abs(o - p) <= TARGET_CALIBRATION for _, n, p, o in calibration if n >= 30)),
        ("Worst 'X% stronger' gap vs truth (bins with >= 10 pairs)",
         f"{max((abs(o - p) for _, n, p, o in stronger if n >= 10), default=0):.3f}",
         f"<= {TARGET_STRONGER}",
         all(abs(o - p) <= TARGET_STRONGER for _, n, p, o in stronger if n >= 10)),
        ("Median rated games until sigma < provisional", f"{median_settle}",
         f"<= {TARGET_CONVERGENCE}", median_settle <= TARGET_CONVERGENCE),
    ]  # fmt: skip

    true_order = sorted(versions, key=lambda v: -strength[versions[v]])
    lines = [
        "# Ratings validation",
        "",
        f"Generated by `scripts/ratings_validation.py --seed {args.seed}` on {date.today()}. "
        "Population: "
        f"{len(POPULATION)} bots (the built-ins at noise 0, 0.25, 0.5 and 0.75, plus random). "
        f"Ground truth: a round robin of {len(truth_games)} games, every map from both seats, "
        "fitted with Bradley-Terry. The ladder: the real matchmaker, worker and live "
        f"ratings, {sum(r.games for r in final.values()) // 2} rated games.",
        "",
        "Targets were fixed in the script before the first run.",
        "",
        "## Checks",
        "",
        "| Check | Result | Target | |",
        "|---|---|---|---|",
        *[f"| {name} | {value} | {target} | {'pass' if ok else '**MISS**'} |"
          for name, value, target, ok in checks],
        "",
        "## Ordering as games accumulate",
        "",
        "| Games per bot | " + " | ".join(str(n) for n in taus) + " |",
        "|---|" + "---|" * len(taus),
        "| Kendall tau | " + " | ".join(f"{t:.3f}" for t in taus.values()) + " |",
        "",
        "## Calibration of P(win)",
        "",
        f"{len(predictions)} games, each predicted from the ratings before it. Brier score "
        f"{brier:.3f} (a coin flip scores 0.25), log loss {log_loss:.3f}.",
        "",
        "| Predicted | Games | Mean predicted | Observed |",
        "|---|---|---|---|",
        *[f"| {label} | {n} | {p:.3f} | {o:.3f} |" for label, n, p, o in calibration],
        "",
        '## "X% stronger" against the truth',
        "",
        "Every pair, oriented so the claim is at least 50%. When the ladder says 80%, the "
        "claimed bot should truly be stronger about 80% of the time.",
        "",
        "| Claimed | Pairs | Mean claimed | Truly stronger |",
        "|---|---|---|---|",
        *[f"| {label} | {n} | {p:.3f} | {o:.3f} |" for label, n, p, o in stronger],
        "",
        "## Final table, in true order",
        "",
        "| Bot | True strength | mu | sigma | games |",
        "|---|---|---|---|---|",
        *[f"| `{versions[v].removeprefix('builtin:')}` | {strength[versions[v]]:.3f} | "
          f"{final[v].mu:.2f} | {final[v].sigma:.2f} | {final[v].games} |" for v in true_order],
        "",
    ]  # fmt: skip
    OUT.write_text("\n".join(lines))
    for name, value, target, ok in checks:
        log.info("%s: %s (target %s) %s", name, value, target, "pass" if ok else "MISS")
    log.info("wrote %s", OUT)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
