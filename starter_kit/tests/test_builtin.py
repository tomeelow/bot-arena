"""The built-in bots are worked examples, so they must play cleanly: whole games without a
single invalid order."""

import pytest
from arena.builtin import BUILTINS, Noisy, builtin_factory
from arena.runner import run_match
from arena_engine import InvalidOrder, new_game, step

SMART = ["greedy", "rush", "turtle", "scout"]


def invalid_orders(record, seat):
    state = new_game(record.rules, record.seed)
    bad = []
    for orders in record.orders:
        result = step(state, {0: orders[0], 1: orders[1]})
        bad += [e for e in result.events[seat] if isinstance(e, InvalidOrder)]
        state = result.state
    return bad


@pytest.mark.parametrize("name", SMART)
@pytest.mark.parametrize("opponent", ["random", "rush", "turtle"])
def test_built_ins_never_send_an_invalid_order(name, opponent):
    record = run_match((f"builtin:{name}", f"builtin:{opponent}"), seed=17)
    assert invalid_orders(record, 0) == []


def test_every_built_in_is_registered_with_a_docstring():
    assert sorted(BUILTINS) == ["greedy", "random", "rush", "scout", "turtle"]
    assert all(cls.__doc__ for cls in BUILTINS.values())


def test_noise_is_part_of_the_name():
    bot = builtin_factory("greedy~0.25")()
    assert isinstance(bot, Noisy)
    assert bot.epsilon == 0.25
    with pytest.raises(ValueError, match="between 0 and 1"):
        builtin_factory("greedy~2")
    with pytest.raises(ValueError, match="no built-in bot"):
        builtin_factory("grede")


def test_full_noise_plays_worse_than_none():
    clean = run_match(("builtin:rush", "builtin:greedy~1"), seed=5).result
    assert clean.winner == 0
