"""Version comparisons: "is my new version better than the old one?"

The owner asks; K seeds are each played from both seats as unrated `comparison` matches, and
the answer comes with a confidence interval and the list of games lost, never as a bare win
count.
"""

import sqlite3
from dataclasses import dataclass
from math import comb
from random import Random

from arena.tournament import wilson

from .ladder import schedule


@dataclass(frozen=True)
class Comparison:
    wins: int
    draws: int
    losses: int
    pending: int
    lost: list[int]  # match ids, to open in the viewer

    @property
    def games(self) -> int:
        return self.wins + self.draws + self.losses

    @property
    def score(self) -> float:
        return (self.wins + self.draws / 2) / self.games if self.games else 0.5

    def interval(self) -> tuple[float, float]:
        return wilson(self.wins + self.draws / 2, self.games)

    def p_better(self) -> float:
        """P(the challenger's true score against the incumbent > 50%), under a uniform prior,
        with each draw counted as half a win and half a loss."""
        a = round(self.wins + self.draws / 2)
        b = round(self.losses + self.draws / 2)
        # For whole numbers, P(Beta(a + 1, b + 1) > 1/2) = P(Binomial(a + b + 1, 1/2) <= a).
        n = a + b + 1
        return sum(comb(n, k) for k in range(a + 1)) / 2**n


def request(
    conn: sqlite3.Connection, challenger: int, incumbent: int, seed_pairs: int, rng: Random
) -> list[int]:
    matches: list[int] = []
    for _ in range(seed_pairs):
        matches += schedule(conn, (challenger, incumbent), "comparison", rng)
    return matches


def report(conn: sqlite3.Connection, challenger: int, incumbent: int) -> Comparison:
    rows = conn.execute(
        """SELECT m.id, m.status, r.winner_seat, mp.seat FROM matches m
           JOIN match_players mp ON mp.match_id = m.id AND mp.bot_version_id = ?
           JOIN match_players other ON other.match_id = m.id AND other.bot_version_id = ?
           LEFT JOIN results r ON r.match_id = m.id
           WHERE m.kind = 'comparison' ORDER BY m.id""",
        (challenger, incumbent),
    ).fetchall()
    wins = draws = losses = pending = 0
    lost: list[int] = []
    for match_id, status, winner, seat in rows:
        if status in ("queued", "running"):
            pending += 1
        elif status == "done" and winner is None:
            draws += 1
        elif status == "done" and winner == seat:
            wins += 1
        elif status == "done":
            losses += 1
            lost.append(match_id)
    return Comparison(wins, draws, losses, pending, lost)
