"""Matchmaking invariants and the leaderboard."""

from random import Random

from arena_server import bots
from arena_server.compare import Comparison, report, request
from arena_server.db import connect, migrate
from arena_server.ladder import leaderboard, next_pairing, place, schedule, top_up
from arena_server.ratings import Ratings
from arena_server.settings import Settings
from hypothesis import given, settings
from hypothesis import strategies as st

SETTINGS = Settings.load()
RATINGS = Ratings(SETTINGS)
ANCHORS = ("random", "greedy", "rush", "turtle", "scout")


def owners_of(db, *versions):
    return {
        db.execute(
            "SELECT b.owner_id FROM bot_versions v JOIN bots b ON b.id = v.bot_id WHERE v.id = ?",
            (v,),
        ).fetchone()[0]
        for v in versions
    }


def players(db, match_id):
    return tuple(
        r[0]
        for r in db.execute(
            "SELECT bot_version_id FROM match_players WHERE match_id = ? ORDER BY seat",
            (match_id,),
        )
    )


def population(db, store, owners: int, bots_each: int):
    for name in ANCHORS:
        bots.builtin_version(db, name)
    for o in range(owners):
        owner = bots.ensure_user(db, f"user{o}", github_id=100 + o)
        for b in range(bots_each):
            v = bots.submit_version(
                db, store, bots.create_bot(db, owner, f"b{b}"), f"#{o}{b}".encode()
            )
            bots.activate(db, v)


@settings(max_examples=25, deadline=None)
@given(owners=st.integers(1, 4), bots_each=st.integers(1, 3), seed=st.integers(0, 10**6))
def test_pairings_never_match_an_owner_against_themself(tmp_path_factory, owners, bots_each, seed):
    path = tmp_path_factory.mktemp("db")
    db = connect(path / "arena.db")
    migrate(db)
    from arena_server.store import Store

    population(db, Store(path / "data"), owners, bots_each)
    rng = Random(seed)
    for _ in range(10):
        pair = next_pairing(db, RATINGS, SETTINGS, rng)
        assert pair is not None
        assert len(owners_of(db, *pair)) == 2
        first, second = schedule(db, pair, "ranked", rng)
        assert players(db, second) == players(db, first)[::-1]
        seeds = {
            r[0] for r in db.execute("SELECT seed FROM matches WHERE id IN (?, ?)", (first, second))
        }
        assert len(seeds) == 1


def test_a_pair_that_played_enough_recently_rests(db, store):
    population(db, store, owners=1, bots_each=1)
    rng = Random(1)
    seen = set()
    for _ in range(40):
        pair = next_pairing(db, RATINGS, SETTINGS, rng)
        if pair is None:
            break
        seen.add(frozenset(pair))
        schedule(db, pair, "ranked", rng)
    counts = db.execute(
        """SELECT count(*) FROM matches m
           JOIN match_players a ON a.match_id = m.id AND a.seat = 0
           JOIN match_players b ON b.match_id = m.id AND b.seat = 1
           GROUP BY min(a.bot_version_id, b.bot_version_id),
                    max(a.bot_version_id, b.bot_version_id)"""
    ).fetchall()
    assert max(c[0] for c in counts) <= SETTINGS.pair_cap + 1  # a mirrored pair lands together
    assert len(seen) > 1


def test_placement_plays_every_anchor_from_both_seats_first(db, store):
    population(db, store, owners=1, bots_each=1)
    owner = bots.ensure_user(db, "new", github_id=999)
    version = bots.submit_version(db, store, bots.create_bot(db, owner, "fresh"), b"# new")
    bots.activate(db, version)
    matches = place(db, version, SETTINGS, Random(3))
    assert len(matches) == len(ANCHORS) * SETTINGS.placement_seed_pairs * 2
    seats = [players(db, m).index(version) for m in matches]
    assert seats.count(0) == seats.count(1)
    priorities = {r[0] for r in db.execute("SELECT priority FROM matches")}
    assert priorities == {SETTINGS.placement_priority}


def test_top_up_keeps_the_queue_at_its_target(db, store):
    population(db, store, owners=2, bots_each=1)
    top_up(db, RATINGS, SETTINGS, Random(4))
    queued = db.execute("SELECT count(*) FROM matches WHERE status = 'queued'").fetchone()[0]
    assert SETTINGS.queue_target <= queued <= SETTINGS.queue_target + 1


def test_the_leaderboard_ranks_by_the_conservative_score(db, store):
    population(db, store, owners=1, bots_each=2)
    db.execute("INSERT INTO ratings VALUES (1, 40.0, 7.0, 3)")  # high mu, still uncertain
    db.execute("INSERT INTO ratings VALUES (2, 30.0, 1.0, 300)")  # lower mu, well known
    board = leaderboard(db, RATINGS)
    top = board[0]
    assert top.entry.version_id == 2 and not top.provisional
    assert next(s for s in board if s.entry.version_id == 1).provisional
    assert [s.rank for s in board] == list(range(1, len(board) + 1))


def test_a_comparison_counts_from_the_challengers_side(db, store):
    population(db, store, owners=1, bots_each=2)
    a, b = 6, 7
    matches = request(db, a, b, seed_pairs=2, rng=Random(5))
    winners = {matches[0]: 0, matches[1]: 0, matches[2]: None}  # seat 0 wins twice, a draw
    for m, w in winners.items():
        db.execute("UPDATE matches SET status = 'done' WHERE id = ?", (m,))
        db.execute(
            "INSERT INTO results (match_id, winner_seat, end_reason, turns, replay_sha256) "
            "VALUES (?, ?, 'turn_limit', 400, 'sha256:x')",
            (m, w),
        )
    result = report(db, a, b)
    assert (result.wins, result.draws, result.losses, result.pending) == (1, 1, 1, 1)
    assert result.lost == [matches[1]]
    assert result.score == 0.5


def test_p_better_reads_the_evidence_the_right_way_round():
    assert Comparison(10, 0, 0, 0, []).p_better() == 1 - 2**-11
    assert Comparison(0, 0, 10, 0, []).p_better() == 2**-11
    assert Comparison(5, 0, 5, 0, []).p_better() == 0.5
    lo, _ = Comparison(30, 0, 10, 0, []).interval()
    assert lo > 0.5


def test_pairing_weight_prefers_even_games_but_never_drops_below_the_floor():
    from arena_server.ladder import pairing_weight
    from arena_server.ratings import Rating

    even = pairing_weight(RATINGS, SETTINGS, Rating(25, 2), Rating(25, 2))
    close = pairing_weight(RATINGS, SETTINGS, Rating(27, 2), Rating(25, 2))
    lopsided = pairing_weight(RATINGS, SETTINGS, Rating(90, 1), Rating(0, 1))
    assert even == 1.0 > close > lopsided == SETTINGS.explore_floor
