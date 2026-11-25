from arena import Bot, Grid, Kind, Observation, Order

from .tactics import Context, Economy, Plan, guard, guard_post

GUARD_DISTANCE = 3
DEFEND_RADIUS2 = 64  # chase enemies within 8 cells of the Core


class TurtleBot(Bot):
    """Defence: a steady economy behind a ring of soldiers that never leaves home."""

    def setup(self) -> None:
        self.ctx = Context(self.map, self.rules, Grid(self.map), self.rng)
        self.economy = Economy(self.ctx)
        self.post = guard_post(self.ctx, GUARD_DISTANCE)

    def act(self, obs: Observation) -> list[Order]:
        plan = Plan(obs, self.ctx)
        workers, soldiers = plan.of_kind(Kind.WORKER), plan.of_kind(Kind.SOLDIER)
        self.economy.plan(plan)
        guard(plan, soldiers, self.post, DEFEND_RADIUS2)
        more_workers = len(workers) < 4 or len(soldiers) >= len(workers)
        plan.spawn(Kind.WORKER if more_workers else Kind.SOLDIER)
        return plan.orders
