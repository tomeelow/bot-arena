from arena import Bot, Grid, Kind, Observation, Order

from .tactics import Context, Economy, Plan

MAX_WORKERS = 14


class GreedyBot(Bot):
    """Pure economy: only workers, mining and banking. Wins on score if nobody attacks it."""

    def setup(self) -> None:
        self.ctx = Context(self.map, self.rules, Grid(self.map), self.rng)
        self.economy = Economy(self.ctx)

    def act(self, obs: Observation) -> list[Order]:
        plan = Plan(obs, self.ctx)
        self.economy.plan(plan)
        if len(plan.of_kind(Kind.WORKER)) < MAX_WORKERS:
            plan.spawn(Kind.WORKER)
        return plan.orders
