"""Round robins: every pairing plays each seed twice, once from each seat, so seat and map
luck cancel out."""

import math
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from itertools import combinations

from .runner import Result, run_match


@dataclass(frozen=True)
class Game:
    a: str
    b: str
    seed: int
    a_seat: int
    result: Result

    def score(self, bot: str) -> float:
        """1 for a win, 0.5 for a draw, 0 for a loss, from `bot`'s side."""
        seat = self.a_seat if bot == self.a else 1 - self.a_seat
        if self.result.winner is None:
            return 0.5
        return 1.0 if self.result.winner == seat else 0.0


def play(job: tuple[str, str, int, int]) -> Game:
    a, b, seed, a_seat = job
    players = (a, b) if a_seat == 0 else (b, a)
    return Game(a, b, seed, a_seat, run_match(players, seed).result)


def round_robin(bots: list[str], seed_pairs: int, jobs: int = 1, first_seed: int = 0) -> list[Game]:
    work = [
        (a, b, seed, a_seat)
        for a, b in combinations(bots, 2)
        for seed in range(first_seed, first_seed + seed_pairs)
        for a_seat in (0, 1)
    ]
    if jobs <= 1:
        return [play(job) for job in work]
    with ProcessPoolExecutor(jobs) as pool:
        return list(pool.map(play, work, chunksize=4))


@dataclass(frozen=True)
class Standing:
    wins: int
    draws: int
    losses: int

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def score(self) -> float:
        return (self.wins + self.draws / 2) / self.games

    def interval(self) -> tuple[float, float]:
        return wilson(self.wins + self.draws / 2, self.games)


def standing(games: Iterable[Game], bot: str, opponent: str) -> Standing:
    scores = [g.score(bot) for g in games if {g.a, g.b} == {bot, opponent}]
    return Standing(scores.count(1.0), scores.count(0.5), scores.count(0.0))


def wilson(successes: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion. Draws count as half a win."""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


def table(games: list[Game], bots: list[str]) -> str:
    """Row bot's score against each column bot, with its 95% interval."""
    names = [b.removeprefix("builtin:") for b in bots]
    width = max(16, *(len(n) for n in names))
    lines = [" " * width + "".join(f"{n:>18}" for n in names)]
    for bot, name in zip(bots, names, strict=True):
        cells = []
        for other in bots:
            if other == bot:
                cells.append(f"{'-':>18}")
                continue
            s = standing(games, bot, other)
            lo, hi = s.interval()
            cells.append(f"{s.score:>6.0%} [{lo:.0%}-{hi:.0%}]".rjust(18))
        lines.append(f"{name:<{width}}" + "".join(cells))
    return "\n".join(lines)
