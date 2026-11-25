import sys
from random import Random

from arena_engine import Event, MapInfo, Observation, Order, Rules


class Bot:
    """Subclass this and implement `act`. One instance plays one whole match.

    Before `setup` runs, the harness sets:
      map     the public map (walls, deposit sites, both Cores), seen from your side
      rules   the match parameters (turn limit, unit cap, mining rate, ...)
      rng     a Random seeded by the match: use it instead of the `random` module so a
              match can be replayed exactly
    Before each `act`, `events` holds your private events from the previous turn.
    """

    map: MapInfo
    rules: Rules
    rng: Random
    events: tuple[Event, ...] = ()

    def setup(self) -> None:
        """Called once before the first turn. Optional."""

    def act(self, obs: Observation) -> list[Order]:
        raise NotImplementedError("your bot must implement act()")

    def log(self, *parts: object) -> None:
        """Write a line to your bot's log, shown in your replays. `print` works too."""
        sys.stdout.write(" ".join(str(p) for p in parts) + "\n")
