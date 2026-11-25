"""The built-in bots: reference opponents, rating anchors and worked examples.

    random   random orders: the floor
    greedy   pure economy
    rush     pure aggression
    turtle   economy behind a defensive ring
    scout    looks first, then counters

`builtin:NAME~EPS` swaps each order for a random one with probability EPS, which gives a
family of bots with a known strength order (used to validate ratings in Phase 5).
"""

from collections.abc import Callable

from arena import DIRS, Bot, Kind, Move, Observation, Order, Spawn

from .greedy import GreedyBot
from .random_bot import RandomBot
from .rush import RushBot
from .scout import ScoutBot
from .turtle import TurtleBot

BUILTINS: dict[str, type[Bot]] = {
    "random": RandomBot,
    "greedy": GreedyBot,
    "rush": RushBot,
    "turtle": TurtleBot,
    "scout": ScoutBot,
}


class Noisy(Bot):
    def __init__(self, inner: Bot, epsilon: float) -> None:
        self.inner = inner
        self.epsilon = epsilon

    def setup(self) -> None:
        self.inner.map, self.inner.rules, self.inner.rng = self.map, self.rules, self.rng
        self.inner.setup()

    def act(self, obs: Observation) -> list[Order]:
        self.inner.events = self.events
        return [
            self._noise(o) if self.rng.random() < self.epsilon else o for o in self.inner.act(obs)
        ]

    def _noise(self, order: Order) -> Order:
        if isinstance(order, Spawn):
            return Spawn(self.rng.choice(list(Kind)), self.rng.choice(DIRS))
        return Move(order.unit, self.rng.choice(DIRS))


def builtin_factory(name: str) -> Callable[[], Bot]:
    base, _, noise = name.partition("~")
    if base not in BUILTINS:
        raise ValueError(f"no built-in bot {base!r}; choose from {sorted(BUILTINS)}")
    cls = BUILTINS[base]
    if not noise:
        return cls
    epsilon = float(noise)
    if not 0 <= epsilon <= 1:
        raise ValueError("noise must be between 0 and 1")
    return lambda: Noisy(cls(), epsilon)
