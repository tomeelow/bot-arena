"""The engine as a two-player environment, for training and evaluation.

Shaped like a PettingZoo ParallelEnv (reset, then step with both seats' orders at once) but
without the dependency: both agents always act, and nothing else is needed. Observations are
the engine's own `observe()`, the same view a jailed bot is sent, so what the boss learns on
is what it plays on. `play` sets bots up exactly as the harness does (map, rules and an rng
seeded `2 * seed + seat`), and tests/test_env.py checks it gives the CLI runner's result and
final state, bit for bit.
"""

import contextlib
import io
from collections.abc import Callable
from dataclasses import dataclass
from random import Random

from arena import Bot, Observation, Order
from arena.runner import Result
from arena_engine import Event, GameState, MapInfo, Rules, map_info, new_game, observe, step

SEATS = (0, 1)


@dataclass
class ArenaEnv:
    rules: Rules

    def reset(self, seed: int) -> tuple[Observation, Observation]:
        self.state = new_game(self.rules, seed)
        self.events: tuple[tuple[Event, ...], tuple[Event, ...]] = ((), ())
        return self._observe()

    def map(self, seat: int) -> MapInfo:
        return map_info(self.state, seat)

    def step(self, orders: tuple[list[Order], list[Order]]) -> tuple[Observation, Observation]:
        result = step(self.state, {0: orders[0], 1: orders[1]})
        self.state, self.events = result.state, result.events
        return self._observe()

    @property
    def done(self) -> bool:
        return self.state.outcome is not None

    def result(self) -> Result:
        outcome = self.state.outcome
        assert outcome is not None, "the match is still running"
        return Result(outcome.winner, outcome.reason.value, outcome.turns)

    def _observe(self) -> tuple[Observation, Observation]:
        return observe(self.state, 0), observe(self.state, 1)


def play(bots: tuple[Bot, Bot], seed: int, rules: Rules | None = None) -> tuple[Result, GameState]:
    """One match between two bot instances, in this process. Their stdout (bot logs) is
    discarded."""
    env = ArenaEnv(rules or Rules())
    obs = env.reset(seed)
    for seat, bot in zip(SEATS, bots, strict=True):
        bot.map, bot.rules, bot.rng = env.map(seat), env.rules, Random(2 * seed + seat)
        _quiet(bot.setup)
    while not env.done:
        orders: list[list[Order]] = []
        for seat, bot in zip(SEATS, bots, strict=True):
            bot.events = env.events[seat]
            orders.append(_quiet(lambda b=bot, o=obs[seat]: b.act(o)))
        obs = env.step((orders[0], orders[1]))
    return env.result(), env.state


def _quiet[T](fn: Callable[[], T]) -> T:
    with contextlib.redirect_stdout(io.StringIO()):
        return fn()
