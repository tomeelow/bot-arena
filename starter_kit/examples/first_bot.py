"""A complete bot to start from: workers mine the nearest deposit and bank the crystals.

Run it:    arena match examples/first_bot.py builtin:random
"""

from arena import (
    DIRS,
    Bot,
    Grid,
    Kind,
    Mine,
    Move,
    Observation,
    Order,
    Spawn,
    Unload,
    adjacent,
    step_pos,
)

FULL = 10  # a worker carries at most 10 crystals


class FirstBot(Bot):
    def setup(self) -> None:
        self.grid = Grid(self.map)  # walls, deposits and Cores never move: build this once
        self.to_core = self.grid.distances([self.map.my_core])
        self.live = set(self.map.deposit_sites)
        self.to_deposits = self.grid.distances(self.live)

    def act(self, obs: Observation) -> list[Order]:
        # Deposit amounts are only visible near your units: forget the ones seen empty.
        empty = {d.pos for d in obs.deposits if d.amount == 0}
        if empty & self.live:
            self.live -= empty
            self.to_deposits = self.grid.distances(self.live)

        orders: list[Order] = []
        occupied = {u.pos for u in obs.units}
        for unit in obs.units:
            if unit.kind is not Kind.WORKER:
                continue
            minable = [d for d in DIRS if step_pos(unit.pos, d) in self.live]
            if unit.cargo > 0 and adjacent(unit.pos, self.map.my_core):
                orders.append(Unload(unit.id))
            elif unit.cargo < FULL and minable:
                orders.append(Mine(unit.id, minable[0]))
            else:
                field = self.to_core if unit.cargo == FULL or not self.live else self.to_deposits
                step = self.grid.step_toward(unit.pos, field, avoid=occupied)
                if step is None:  # our own units are in the way: sometimes step aside so jams clear
                    free = [d for d, n in self.grid.open_neighbours(unit.pos) if n not in occupied]
                    step = self.rng.choice(free) if free and self.rng.random() < 0.5 else None
                if step is not None:
                    occupied.discard(unit.pos)
                    occupied.add(step_pos(unit.pos, step))
                    orders.append(Move(unit.id, step))

        workers = sum(u.kind is Kind.WORKER for u in obs.units)
        if obs.bank >= 50 and workers < 6:
            orders.append(Spawn(Kind.WORKER, self.rng.choice(DIRS)))
        self.log(f"turn {obs.turn}: {workers} workers, {obs.bank} banked")
        return orders
