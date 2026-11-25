"""The `arena` command: play, inspect and compare bots on your own machine.

arena match my_bot.py builtin:greedy --seed 7
arena show replay.json.gz --turn 120
arena tournament my_bot.py builtin:rush builtin:turtle --seed-pairs 20
"""

import argparse
import os
import sys
from pathlib import Path
from random import SystemRandom

from .builtin import BUILTINS, builtin_factory
from .render import render
from .replay import ReplayError, load, save, save_logs
from .runner import run_match
from .tournament import round_robin, table

DESCRIPTION = "Play, inspect and compare Bot Arena bots on your own machine."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="arena", description=DESCRIPTION)
    commands = parser.add_subparsers(dest="command", required=True)

    match = commands.add_parser("match", help="play one match and save its replay")
    match.add_argument("bots", nargs=2, help=f"a .py file or builtin:NAME ({', '.join(BUILTINS)})")
    match.add_argument("--seed", type=int, help="map seed (random if omitted)")
    match.add_argument("--out", type=Path, default=Path("replay.json.gz"))
    match.add_argument("--logs", type=Path, help="also save the bots' logs here")

    show = commands.add_parser("show", help="print the board from a replay")
    show.add_argument("replay", type=Path)
    show.add_argument("--turn", type=int, help="turn to show (the last one if omitted)")

    tour = commands.add_parser("tournament", help="round robin, every seed from both seats")
    tour.add_argument("bots", nargs="+")
    tour.add_argument("--seed-pairs", type=int, default=10)
    tour.add_argument("--jobs", type=int, default=os.cpu_count() or 1)

    args = parser.parse_args(argv)
    if problems := [p for spec in getattr(args, "bots", []) if (p := _check_spec(spec))]:
        for problem in problems:
            print(f"arena: {problem}", file=sys.stderr)
        return 2
    match args.command:
        case "match":
            return _match(args.bots, args.seed, args.out, args.logs)
        case "show":
            return _show(args.replay, args.turn)
        case _:
            games = round_robin(args.bots, args.seed_pairs, args.jobs)
            print(f"{len(games)} games. Each cell: row bot's score against the column bot.")
            print(table(games, args.bots))
            return 0


def _check_spec(spec: str) -> str | None:
    """Catch typos before a match starts. Only checks that a file exists: the host never
    imports a bot's code."""
    if spec.startswith("builtin:"):
        try:
            builtin_factory(spec.removeprefix("builtin:"))
        except ValueError as e:
            return str(e)
        return None
    if not Path(spec).is_file():
        return f"no such bot file: {spec}"
    return None


def _match(bots: list[str], seed: int | None, out: Path, logs: Path | None) -> int:
    seed = SystemRandom().randrange(2**31) if seed is None else seed
    record = run_match((bots[0], bots[1]), seed)
    result = record.result
    print(f"seed {seed}: seat 0 {bots[0]} vs seat 1 {bots[1]}")
    if result.winner is None:
        print(f"draw ({result.reason}) after {result.turns} turns")
    else:
        winner = bots[result.winner]
        print(f"seat {result.winner} ({winner}) wins: {result.reason}, turn {result.turns}")
    if result.detail:
        print(result.detail)
    for seat, err in enumerate(record.stderr):
        if err.strip():
            print(f"--- seat {seat} stderr ---\n{err.rstrip()}")
    for note in record.warnings:
        print(f"warning: {note}")
    save(record, out)
    print(f"replay: {out}")
    if logs:
        save_logs(record, logs)
        print(f"logs: {logs}")
    return 0


def _show(path: Path, turn: int | None) -> int:
    try:
        replay = load(path)
    except ReplayError as e:
        print(f"cannot show {path}: {e}", file=sys.stderr)
        return 1
    last = len(replay.states) - 1
    index = last if turn is None else max(0, min(turn, last))
    print(render(replay.states[index]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
