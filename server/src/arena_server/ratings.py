"""Ratings (ADR-003): OpenSkill Weng-Lin, one (mu, sigma) per bot version.

Results are the source of truth. Ratings are a fold over rated results in the order they
were recorded; the live table is updated with the same function inside the transaction that
records each result, so it always equals a rebuild.
"""

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from math import erf, sqrt

from openskill.models import PlackettLuce

from .settings import Settings

RATED_KINDS = ("ranked", "placement")


@dataclass(frozen=True)
class Rating:
    mu: float
    sigma: float
    games: int = 0


class Ratings:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = PlackettLuce(
            mu=settings.mu, sigma=settings.sigma, beta=settings.beta, tau=settings.tau
        )

    def prior(self, parent: Rating | None = None) -> Rating:
        """A new version starts from its parent's mu with full uncertainty: a head start that
        stays honest, because sigma is wide."""
        return Rating(parent.mu if parent else self.settings.mu, self.settings.sigma)

    def update(self, a: Rating, b: Rating, winner: int | None) -> tuple[Rating, Rating]:
        ranks = [0.0, 0.0] if winner is None else [float(winner), float(1 - winner)]
        [[ra], [rb]] = self.model.rate(
            [[self.model.rating(a.mu, a.sigma)], [self.model.rating(b.mu, b.sigma)]], ranks=ranks
        )
        return Rating(ra.mu, ra.sigma, a.games + 1), Rating(rb.mu, rb.sigma, b.games + 1)

    def p_stronger(self, a: Rating, b: Rating) -> float:
        """P(skill a > skill b): a statement about skill, not about the next game."""
        return _phi((a.mu - b.mu) / sqrt(a.sigma**2 + b.sigma**2))

    def p_win(self, a: Rating, b: Rating) -> float:
        """P(a beats b in one game): adds each side's per-game performance noise."""
        beta = self.settings.beta
        return _phi((a.mu - b.mu) / sqrt(a.sigma**2 + b.sigma**2 + 2 * beta**2))

    def conservative(self, r: Rating) -> float:
        return r.mu - self.settings.conservative_k * r.sigma

    def provisional(self, r: Rating) -> bool:
        return r.sigma > self.settings.provisional_sigma


def _phi(z: float) -> float:
    return 0.5 * (1 + erf(z / sqrt(2)))


def rated_results(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        f"""SELECT r.match_id, r.winner_seat, p0.bot_version_id AS v0, p1.bot_version_id AS v1
            FROM results r
            JOIN matches m ON m.id = r.match_id
            JOIN match_players p0 ON p0.match_id = r.match_id AND p0.seat = 0
            JOIN match_players p1 ON p1.match_id = r.match_id AND p1.seat = 1
            WHERE m.kind IN {RATED_KINDS!r}
            ORDER BY r.rowid"""
    ).fetchall()


def fold(
    conn: sqlite3.Connection, ratings: Ratings
) -> Iterator[tuple[sqlite3.Row, Rating, Rating]]:
    """Each rated result in order, with both players' ratings after it."""
    parents: dict[int, int | None] = dict(
        conn.execute("SELECT id, parent_id FROM bot_versions").fetchall()
    )
    table: dict[int, Rating] = {}

    def current(version: int) -> Rating:
        if version in table:
            return table[version]
        parent = parents.get(version)
        return ratings.prior(table.get(parent) if parent is not None else None)

    for row in rated_results(conn):
        a, b = ratings.update(current(row["v0"]), current(row["v1"]), row["winner_seat"])
        table[row["v0"]], table[row["v1"]] = a, b
        yield row, a, b


def rebuild(conn: sqlite3.Connection, ratings: Ratings) -> dict[int, Rating]:
    """Every rating, recomputed from the results alone."""
    table: dict[int, Rating] = {}
    for row, a, b in fold(conn, ratings):
        table[row["v0"]], table[row["v1"]] = a, b
    return table


def history(
    conn: sqlite3.Connection, ratings: Ratings, version_ids: set[int]
) -> list[tuple[int, int, Rating]]:
    """(match id, version id, rating after it) for every rated game these versions played.
    Replays the whole fold, so it is exactly what the live table went through."""
    points = []
    for row, a, b in fold(conn, ratings):
        for version, rating in ((row["v0"], a), (row["v1"], b)):
            if version in version_ids:
                points.append((row["match_id"], version, rating))
    return points


def stored(conn: sqlite3.Connection) -> dict[int, Rating]:
    rows = conn.execute("SELECT bot_version_id, mu, sigma, games FROM ratings").fetchall()
    return {r[0]: Rating(r[1], r[2], r[3]) for r in rows}


def apply(conn: sqlite3.Connection, match_id: int, ratings: Ratings) -> None:
    """Fold one new result into the live table. Call inside the transaction that records it."""
    row = conn.execute(
        """SELECT m.kind, r.winner_seat, p0.bot_version_id, p1.bot_version_id
           FROM results r JOIN matches m ON m.id = r.match_id
           JOIN match_players p0 ON p0.match_id = r.match_id AND p0.seat = 0
           JOIN match_players p1 ON p1.match_id = r.match_id AND p1.seat = 1
           WHERE r.match_id = ?""",
        (match_id,),
    ).fetchone()
    kind, winner, v0, v1 = row
    if kind not in RATED_KINDS:
        return
    a, b = ratings.update(_current(conn, v0, ratings), _current(conn, v1, ratings), winner)
    conn.executemany(
        """INSERT INTO ratings (bot_version_id, mu, sigma, games) VALUES (?, ?, ?, ?)
           ON CONFLICT (bot_version_id) DO UPDATE
           SET mu = excluded.mu, sigma = excluded.sigma, games = excluded.games""",
        [(v0, a.mu, a.sigma, a.games), (v1, b.mu, b.sigma, b.games)],
    )


def _current(conn: sqlite3.Connection, version: int, ratings: Ratings) -> Rating:
    own = conn.execute(
        "SELECT mu, sigma, games FROM ratings WHERE bot_version_id = ?", (version,)
    ).fetchone()
    if own:
        return Rating(*own)
    parent = conn.execute(
        """SELECT r.mu, r.sigma, r.games FROM bot_versions v
           JOIN ratings r ON r.bot_version_id = v.parent_id WHERE v.id = ?""",
        (version,),
    ).fetchone()
    return ratings.prior(Rating(*parent) if parent else None)
