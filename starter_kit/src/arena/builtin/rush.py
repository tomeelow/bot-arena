from arena import Bot, Grid, Kind, Observation, Order

from .tactics import Context, Economy, Plan, march

WORKERS = 3


class RushBot(Bot):
    """All-in aggression: a few workers fund a stream of soldiers that march straight at the
    enemy Core and fight whatever they meet."""

    def setup(self) -> None:
        self.ctx = Context(self.map, self.rules, Grid(self.map), self.rng)
        self.economy = Economy(self.ctx)
        self.to_enemy = self.ctx.grid.distances([self.map.enemy_core])

    def act(self, obs: Observation) -> list[Order]:
        plan = Plan(obs, self.ctx)
        self.economy.plan(plan)
        march(plan, plan.of_kind(Kind.SOLDIER), self.to_enemy)
        plan.spawn(Kind.WORKER if len(plan.of_kind(Kind.WORKER)) < WORKERS else Kind.SOLDIER)
        return plan.orders
