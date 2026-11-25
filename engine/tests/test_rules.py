"""One test per rule and worked example in docs/GAME_RULES.md §4-§7."""

from dataclasses import replace

import pytest
from engine_support import alive, rel, scenario, unit

from arena_engine import (
    Attack,
    Dir,
    EndReason,
    InvalidOrder,
    Kind,
    Mine,
    Move,
    Pos,
    Spawn,
    SpawnBlocked,
    UnitLost,
    Unload,
    step,
)

E, W, N, S = Dir.E, Dir.W, Dir.N, Dir.S


def positions(state, seat):
    return {u.id: u.pos for u in state.units if u.seat == seat}


# --- §5 phase 3: moves -------------------------------------------------------------------


def test_move_into_free_cell():
    s = scenario("C....", ".W...", "....c")
    after = step(s, {0: [Move(1, E)]}).state
    assert positions(after, 0) == {1: Pos(2, 1)}


def test_units_contesting_a_cell_all_stay():
    s = scenario("C....", ".W.w.", "....c")
    after = step(s, {0: [Move(1, E)], 1: [Move(1, rel(1, W))]}).state
    assert positions(after, 0) == {1: Pos(1, 1)}
    assert positions(after, 1) == {1: Pos(3, 1)}


def test_swapping_units_both_stay():
    s = scenario("C....", ".Ww..", "....c")
    after = step(s, {0: [Move(1, E)], 1: [Move(1, rel(1, W))]}).state
    assert positions(after, 0) == {1: Pos(1, 1)}
    assert positions(after, 1) == {1: Pos(2, 1)}


def test_chain_moves_when_the_front_unit_leaves():
    s = scenario("C....", ".WW..", "....c")
    after = step(s, {0: [Move(1, E), Move(2, E)]}).state
    assert positions(after, 0) == {1: Pos(2, 1), 2: Pos(3, 1)}


def test_chain_is_blocked_when_the_front_unit_holds():
    s = scenario("C....", ".WW..", "....c")
    after = step(s, {0: [Move(1, E)]}).state
    assert positions(after, 0) == {1: Pos(1, 1), 2: Pos(2, 1)}


def test_a_ring_of_units_rotates():
    s = scenario("C...", ".WW.", ".WW.", "...c")
    after = step(s, {0: [Move(1, E), Move(2, S), Move(4, W), Move(3, N)]}).state
    assert positions(after, 0) == {1: Pos(2, 1), 2: Pos(2, 2), 3: Pos(1, 1), 4: Pos(1, 2)}


@pytest.mark.parametrize("d", [N, E, W])  # wall, deposit, Core
def test_moving_into_terrain_is_invalid(d):
    s = scenario("C#...", "CW$..", "....c")
    result = step(s, {0: [Move(1, d)]})
    assert positions(result.state, 0) == {1: Pos(1, 1)}
    assert result.events[0] == (InvalidOrder(Move(1, d), "cannot move onto that cell"),)


def test_a_cell_emptied_by_a_death_can_be_entered():
    s = scenario("C....", "SwW..", "....c", hp={(1, 1): 5})
    after = step(s, {0: [Attack(1, E), Move(2, W)]}).state
    assert unit(after, 1, 1) is None
    assert positions(after, 0) == {1: Pos(0, 1), 2: Pos(1, 1)}


# --- §5 phases 1-2: attacks and deaths ---------------------------------------------------


def test_adjacent_soldiers_can_kill_each_other():
    s = scenario("C....", ".Ss..", "....c", hp={(0, 1): 5, (1, 1): 5})
    result = step(s, {0: [Attack(1, E)], 1: [Attack(1, rel(1, W))]})
    assert result.state.units == ()
    assert result.events == (
        (UnitLost(1, Pos(1, 1)),),
        (UnitLost(1, Pos(4 - 2, 2 - 1)),),
    )


def test_moving_away_does_not_dodge_an_attack():
    s = scenario("C....", ".Sw..", "....c")
    after = step(s, {0: [Attack(1, E)], 1: [Move(1, rel(1, E))]}).state
    survivor = unit(after, 1, 1)
    assert survivor is not None
    assert survivor.pos == Pos(3, 1)
    assert survivor.hp == 5


def test_damage_from_several_attackers_stacks():
    s = scenario("C.S..", ".SwS.", "....c")
    after = step(s, {0: [Attack(1, S), Attack(2, E), Attack(3, W)]}).state
    assert unit(after, 1, 1) is None


def test_a_dead_workers_cargo_is_lost():
    s = scenario("C....", ".Sw..", "....c", hp={(1, 1): 5}, cargo={(1, 1): 4})
    after = step(s, {0: [Attack(1, E)]}).state
    assert after.lost == 4


@pytest.mark.parametrize(
    ("rows", "order", "reason"),
    [
        (("C....", ".S...", "....c"), Attack(1, E), "no enemy there"),
        (("C....", ".SW..", "....c"), Attack(1, E), "no enemy there"),
        (("C....", ".Ww..", "....c"), Attack(1, E), "this unit cannot attack"),
    ],
)
def test_invalid_attacks(rows, order, reason):
    result = step(scenario(*rows), {0: [order]})
    assert result.events[0] == (InvalidOrder(order, reason),)


# --- §5 phase 4: mining and unloading ----------------------------------------------------


def test_a_short_deposit_is_split_evenly():
    s = scenario("C....", ".W$w.", "....c", amounts={Pos(2, 1): 3})
    after = step(s, {0: [Mine(1, E)], 1: [Mine(1, rel(1, W))]}).state
    assert (alive(after, 0, 1).cargo, alive(after, 1, 1).cargo) == (1, 1)
    assert after.deposits[0].amount == 1


def test_mining_stops_at_full_cargo():
    s = scenario("C....", ".W$..", "....c", cargo={(0, 1): 9})
    after = step(s, {0: [Mine(1, E)]}).state
    assert alive(after, 0, 1).cargo == 10
    assert after.deposits[0].amount == 99


@pytest.mark.parametrize(
    ("cargo", "amount", "reason"),
    [(10, 100, "cargo is full"), (0, 0, "no crystals there")],
)
def test_invalid_mining(cargo, amount, reason):
    s = scenario("C....", ".W$..", "....c", cargo={(0, 1): cargo}, amounts={Pos(2, 1): amount})
    result = step(s, {0: [Mine(1, E)]})
    assert result.events[0] == (InvalidOrder(Mine(1, E), reason),)


def test_unloading_next_to_the_core_banks_the_cargo():
    s = scenario("CW...", ".....", "....c", cargo={(0, 1): 6}, banks=(10, 0))
    after = step(s, {0: [Unload(1)]}).state
    assert after.banks == (16, 0)
    assert alive(after, 0, 1).cargo == 0


def test_unloading_away_from_the_core_is_invalid():
    s = scenario("C.W..", ".....", "....c", cargo={(0, 1): 6})
    result = step(s, {0: [Unload(1)]})
    assert result.events[0] == (InvalidOrder(Unload(1), "not next to your core"),)


# --- §5 phase 5: spawns ------------------------------------------------------------------


def test_spawning_creates_a_unit_and_spends_crystals():
    s = scenario("C....", ".....", "....c", banks=(100, 0))
    after = step(s, {0: [Spawn(Kind.SOLDIER, E)]}).state
    new = unit(after, 0, 1)
    assert new is not None
    assert (new.kind, new.pos, new.hp) == (Kind.SOLDIER, Pos(1, 0), 30)
    assert (after.banks, after.spent, after.next_id) == ((20, 0), (80, 0), (2, 1))


def test_a_spawn_into_a_cell_entered_this_turn_fails_and_costs_nothing():
    s = scenario("C.W..", ".....", "....c", banks=(100, 0))
    result = step(s, {0: [Spawn(Kind.WORKER, E), Move(1, W)]})
    assert positions(result.state, 0) == {1: Pos(1, 0)}
    assert result.state.banks == (100, 0)
    assert result.events[0] == (SpawnBlocked(Kind.WORKER, Pos(1, 0)),)


@pytest.mark.parametrize(
    ("bank", "max_units", "reason"),
    [(10, 40, "not enough crystals"), (100, 1, "unit limit reached")],
)
def test_invalid_spawns(bank, max_units, reason):
    s = scenario("C....", "...W.", "....c", banks=(bank, 0), max_units=max_units)
    result = step(s, {0: [Spawn(Kind.WORKER, E)]})
    assert result.events[0] == (InvalidOrder(Spawn(Kind.WORKER, E), reason),)


def test_two_spawns_in_one_turn_are_both_invalid():
    s = scenario("C....", ".....", "....c", banks=(500, 0))
    spawns = [Spawn(Kind.WORKER, E), Spawn(Kind.SCOUT, S)]
    result = step(s, {0: spawns})
    assert result.state.units == ()
    assert result.events[0] == tuple(
        InvalidOrder(o, "more than one spawn this turn") for o in spawns
    )


# --- §4: order validity ------------------------------------------------------------------


def test_every_order_for_a_unit_given_two_is_invalid():
    s = scenario("C....", ".W...", "....c")
    orders = [Move(1, E), Move(1, S)]
    result = step(s, {0: orders})
    assert positions(result.state, 0) == {1: Pos(1, 1)}
    assert result.events[0] == tuple(
        InvalidOrder(o, "more than one order for this unit") for o in orders
    )


def test_orders_for_units_you_do_not_own_are_invalid():
    s = scenario("C....", ".w...", "....c")
    result = step(s, {0: [Move(1, E)]})
    assert result.events == ((InvalidOrder(Move(1, E), "no such unit"),), ())


def test_seat_one_orders_are_in_its_own_frame():
    s = scenario("C....", "..w..", "....c")
    after = step(s, {1: [Move(1, N)]}).state
    assert positions(after, 1) == {1: Pos(2, 2)}


def test_invalid_order_reports_use_the_senders_frame():
    s = scenario("C....", ".....", "..w#c")
    result = step(s, {1: [Move(1, W)]})  # seat 1's west is absolute east: the wall
    assert result.events[1] == (InvalidOrder(Move(1, W), "cannot move onto that cell"),)


# --- §7: ending and scoring --------------------------------------------------------------


def test_destroying_the_enemy_core_wins():
    s = scenario("C....", ".....", "...Sc")
    s = replace(s, cores=(s.cores[0], replace(s.cores[1], hp=5)))
    after = step(s, {0: [Attack(1, E)]}).state
    assert after.outcome is not None
    assert (after.outcome.winner, after.outcome.reason) == (0, EndReason.CORE_DESTROYED)


def test_both_cores_falling_together_is_a_draw():
    s = scenario("Cs...", ".....", "...Sc")
    s = replace(s, cores=(replace(s.cores[0], hp=5), replace(s.cores[1], hp=5)))
    after = step(s, {0: [Attack(1, E)], 1: [Attack(1, rel(1, W))]}).state
    assert after.outcome is not None
    assert (after.outcome.winner, after.outcome.reason) == (None, EndReason.CORE_DESTROYED)


@pytest.mark.parametrize(("banks", "winner"), [((10, 5), 0), ((5, 10), 1), ((7, 7), None)])
def test_turn_limit_goes_to_the_higher_score(banks, winner):
    s = scenario("C....", ".....", "....c", banks=banks, max_turns=1)
    after = step(s, {}).state
    assert after.outcome is not None
    assert (after.outcome.winner, after.outcome.reason) == (winner, EndReason.TURN_LIMIT)


def test_score_counts_bank_cargo_and_unit_costs():
    s = scenario("CW...", ".....", "...xc", banks=(5, 0), cargo={(0, 1): 3}, max_turns=1)
    after = step(s, {}).state
    assert after.outcome is not None
    assert after.outcome.winner == 0  # 5 + 3 + 50 beats 0 + 30


def test_stepping_a_finished_game_is_an_error():
    s = scenario("C....", ".....", "....c", max_turns=1)
    after = step(s, {}).state
    with pytest.raises(ValueError, match="over"):
        step(after, {})
