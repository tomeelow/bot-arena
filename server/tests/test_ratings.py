"""Ratings are derived: the live table must equal a rebuild from results, exactly."""

import plays
from arena_server import bots, queue
from arena_server.ladder import schedule
from arena_server.ratings import Rating, Ratings, rebuild, stored
from arena_server.settings import Settings
from arena_server.worker import Worker

RATINGS = Ratings(Settings.load())


def drain(worker):
    while worker.step():
        pass


def anchors(db):
    return {n: bots.builtin_version(db, n) for n in ("random", "greedy", "rush")}


def test_live_ratings_equal_a_rebuild_from_results(db, store):
    a = anchors(db)
    owner = bots.ensure_user(db, "ada", github_id=1)
    mine = bots.create_bot(db, owner, "mine")
    v1 = bots.submit_version(
        db,
        store,
        mine,
        b"from arena.builtin.rush import RushBot as R\n\nclass Mine(R):\n    pass\n",
    )
    worker = Worker(db, store, plays.quick)
    drain(worker)  # validation, then placement against every anchor
    for pair in [(a["random"], a["greedy"]), (a["rush"], a["random"]), (v1, a["rush"])]:
        schedule(db, pair, "ranked", worker.rng)
    drain(worker)
    live = stored(db)
    assert live == rebuild(db, RATINGS)
    assert sum(r.games for r in live.values()) == 2 * len(
        db.execute("SELECT 1 FROM matches WHERE kind IN ('ranked', 'placement')").fetchall()
    )


def test_unrated_and_void_matches_never_move_a_rating(db, store):
    a = anchors(db)
    worker = Worker(db, store, plays.quick)
    schedule(db, (a["random"], a["greedy"]), "comparison", worker.rng)
    for match in schedule(db, (a["rush"], a["greedy"]), "ranked", worker.rng):
        queue.void(db, match, "test")
    drain(worker)
    assert stored(db) == {}
    assert rebuild(db, RATINGS) == {}


def test_a_win_moves_both_ratings_the_right_way():
    prior = RATINGS.prior()
    winner, loser = RATINGS.update(prior, prior, winner=0)
    assert winner.mu > prior.mu > loser.mu
    assert winner.sigma < prior.sigma and loser.sigma < prior.sigma
    assert (winner.games, loser.games) == (1, 1)
    drawn = RATINGS.update(prior, prior, winner=None)
    assert drawn[0].mu == drawn[1].mu == prior.mu


def test_a_new_version_starts_from_its_parents_mu_with_full_uncertainty():
    parent = Rating(31.0, 1.5, 200)
    child = RATINGS.prior(parent)
    assert (child.mu, child.sigma, child.games) == (31.0, RATINGS.prior().sigma, 0)


def test_stronger_than_is_not_the_same_as_wins_the_next_game():
    a, b = Rating(30, 2), Rating(25, 2)
    assert RATINGS.p_stronger(a, b) + RATINGS.p_stronger(b, a) == 1
    assert 0.5 < RATINGS.p_win(a, b) < RATINGS.p_stronger(a, b)
    assert RATINGS.p_stronger(a, a) == 0.5
