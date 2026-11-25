from arena import Bot, Grid, Kind, Observation, Order, dist2

from .tactics import Context, Economy, Plan, guard, guard_post, march

DEFEND_RADIUS2 = 64
DECIDE_BY_TURN = 60  # no army seen by then: the enemy is greedy, so go and punish it


class ScoutBot(Bot):
    """Information first: a scout goes to look, then the bot counters what it saw.

    Enemy soldiers heading our way -> defend. Enemy soldiers sitting at home -> out-mine
    them. Nothing but workers -> attack.
    """

    def setup(self) -> None:
        self.ctx = Context(self.map, self.rules, Grid(self.map), self.rng)
        self.economy = Economy(self.ctx)
        self.post = guard_post(self.ctx, 3)
        self.to_enemy = self.ctx.grid.distances([self.map.enemy_core])
        self.mode = "scout"

    def act(self, obs: Observation) -> list[Order]:
        self.mode = self._read_enemy(obs)
        plan = Plan(obs, self.ctx)
        workers, soldiers = plan.of_kind(Kind.WORKER), plan.of_kind(Kind.SOLDIER)
        scouts = plan.of_kind(Kind.SCOUT)

        self.economy.plan(plan)
        march(plan, scouts, self.to_enemy)
        if self.mode == "attack":
            march(plan, soldiers, self.to_enemy)
        else:
            guard(plan, soldiers, self.post, DEFEND_RADIUS2)

        if not scouts and obs.turn < DECIDE_BY_TURN:
            plan.spawn(Kind.SCOUT)
        elif len(workers) < 4 or (self.mode == "out-mine" and len(soldiers) >= 2):
            plan.spawn(Kind.WORKER)
        elif self.mode == "scout":
            plan.spawn(Kind.WORKER if len(workers) < 6 else Kind.SOLDIER)
        else:
            plan.spawn(Kind.SOLDIER)
        self.log(f"turn {obs.turn}: {self.mode}")
        return plan.orders

    def _read_enemy(self, obs: Observation) -> str:
        if self.mode in ("defend", "attack"):
            return self.mode
        for e in obs.enemies:
            if e.kind is not Kind.SOLDIER:
                continue
            if dist2(e.pos, self.map.my_core) < dist2(e.pos, self.map.enemy_core):
                return "defend"
            self.mode = "out-mine"
        if self.mode == "scout" and obs.turn >= DECIDE_BY_TURN:
            return "attack"
        return self.mode
