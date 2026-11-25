from arena import DIRS, Attack, Bot, Kind, Mine, Move, Observation, Order, Spawn, Unload


class RandomBot(Bot):
    """Random orders, many of them invalid. The floor every real bot should clear."""

    def act(self, obs: Observation) -> list[Order]:
        orders: list[Order] = []
        for u in obs.units:
            d = self.rng.choice(DIRS)
            options: list[Order] = [Move(u.id, d)]
            if u.kind is Kind.WORKER:
                options += [Mine(u.id, d), Unload(u.id)]
            if u.kind is Kind.SOLDIER:
                options.append(Attack(u.id, d))
            if self.rng.randrange(5):
                orders.append(self.rng.choice(options))
        if self.rng.randrange(3) == 0:
            orders.append(Spawn(self.rng.choice(list(Kind)), self.rng.choice(DIRS)))
        return orders
