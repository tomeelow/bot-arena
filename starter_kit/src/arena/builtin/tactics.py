"""Building blocks the built-in bots share. Read the bots first; this is the plumbing."""

from dataclasses import dataclass
from random import Random

from arena import (
    DIRS,
    UNIT_STATS,
    Attack,
    Dir,
    Grid,
    Kind,
    MapInfo,
    Mine,
    Move,
    Observation,
    Order,
    OwnUnit,
    Pos,
    Rules,
    SeenUnit,
    Spawn,
    Unload,
    adjacent,
    dist2,
    step_pos,
)

CROWD_PENALTY = 4  # extra steps a worker accepts to avoid sharing a deposit


@dataclass(frozen=True)
class Context:
    """What a bot knows for the whole match."""

    map: MapInfo
    rules: Rules
    grid: Grid
    rng: Random


class Plan:
    """One turn's orders, plus the cells our own units will occupy, so they don't walk into
    each other."""

    def __init__(self, obs: Observation, ctx: Context) -> None:
        self.obs = obs
        self.ctx = ctx
        self.orders: list[Order] = []
        self.taken = {u.pos for u in obs.units}

    def add(self, order: Order) -> None:
        self.orders.append(order)

    def go(self, unit: OwnUnit, field: dict[Pos, int]) -> None:
        """Step down `field`. When our own units block every way down, sometimes shuffle
        aside instead: two units meeting head-on in a corridor would otherwise wait forever."""
        grid, rng = self.ctx.grid, self.ctx.rng
        d = grid.step_toward(unit.pos, field, self.taken)
        if d is None and rng.random() < 0.5:
            free = [d for d, n in grid.open_neighbours(unit.pos) if n not in self.taken]
            d = rng.choice(free) if free else None
        if d is not None:
            self.taken.discard(unit.pos)
            self.taken.add(step_pos(unit.pos, d))
            self.orders.append(Move(unit.id, d))

    def spawn(self, kind: Kind) -> None:
        """Spawn next to the Core, if affordable and a neighbouring cell is free."""
        obs, ctx = self.obs, self.ctx
        if obs.bank < UNIT_STATS[kind].cost or len(obs.units) >= ctx.rules.max_units:
            return
        for d in DIRS:
            cell = step_pos(ctx.map.my_core, d)
            if ctx.grid.passable(cell) and cell not in self.taken:
                self.taken.add(cell)
                self.orders.append(Spawn(kind, d))
                return

    def of_kind(self, kind: Kind) -> list[OwnUnit]:
        return [u for u in self.obs.units if u.kind is kind]


class Economy:
    """Workers mine the closest deposit that still has crystals, spreading out rather than
    queueing at one, and carry full loads home."""

    def __init__(self, ctx: Context) -> None:
        self.ctx = ctx
        self.home = ctx.grid.distances([ctx.map.my_core])
        self.site_fields = {s: ctx.grid.distances([s]) for s in ctx.map.deposit_sites}
        self.known: dict[Pos, int] = {}

    def plan(self, plan: Plan) -> None:
        for d in plan.obs.deposits:
            self.known[d.pos] = d.amount
        live = [s for s in self.site_fields if self.known.get(s, 1) > 0]
        heading = dict.fromkeys(live, 0)
        carry = UNIT_STATS[Kind.WORKER].carry
        for w in plan.of_kind(Kind.WORKER):
            if w.cargo > 0 and adjacent(w.pos, self.ctx.map.my_core):
                plan.add(Unload(w.id))
            elif w.cargo >= carry or (w.cargo > 0 and not live):
                plan.go(w, self.home)
            elif mineable := [d for d in DIRS if step_pos(w.pos, d) in heading]:
                plan.add(Mine(w.id, mineable[0]))
                heading[step_pos(w.pos, mineable[0])] += 1
            elif reachable := [s for s in live if w.pos in self.site_fields[s]]:
                site = min(
                    reachable,
                    key=lambda s: self.site_fields[s][w.pos] + CROWD_PENALTY * heading[s],
                )
                heading[site] += 1
                plan.go(w, self.site_fields[site])


def attack_adjacent(unit: OwnUnit, plan: Plan) -> Order | None:
    """Hit the most dangerous adjacent enemy (soldiers first, then the weakest), or the
    enemy Core."""
    by_pos: dict[Pos, SeenUnit] = {e.pos: e for e in plan.obs.enemies}
    targets: list[tuple[int, int, Dir]] = []
    for d in DIRS:
        cell = step_pos(unit.pos, d)
        if (e := by_pos.get(cell)) is not None:
            targets.append((0 if e.kind is Kind.SOLDIER else 1, e.hp, d))
        elif cell == plan.ctx.map.enemy_core:
            targets.append((2, 0, d))
    return Attack(unit.id, min(targets)[2]) if targets else None


def march(plan: Plan, units: list[OwnUnit], field: dict[Pos, int]) -> None:
    """Soldiers fight whatever is adjacent; everyone else (and soldiers with nothing to hit)
    walks down `field`."""
    for u in units:
        hit = attack_adjacent(u, plan) if u.kind is Kind.SOLDIER else None
        if hit is not None:
            plan.add(hit)
        else:
            plan.go(u, field)


def guard(plan: Plan, soldiers: list[OwnUnit], post: dict[Pos, int], radius2: int) -> None:
    """Hold a ring around the Core; chase enemies that come within `radius2` of it."""
    core = plan.ctx.map.my_core
    threats = [e.pos for e in plan.obs.enemies if dist2(e.pos, core) <= radius2]
    chase = plan.ctx.grid.distances(threats) if threats else None
    for s in soldiers:
        if (hit := attack_adjacent(s, plan)) is not None:
            plan.add(hit)
        elif chase is not None:
            plan.go(s, chase)
        elif post.get(s.pos, 0) > 0:
            plan.go(s, post)


def guard_post(ctx: Context, distance: int) -> dict[Pos, int]:
    """Distances to the ring of cells `distance` steps from the Core: out of the way of
    workers and spawns, close enough to defend."""
    home = ctx.grid.distances([ctx.map.my_core])
    return ctx.grid.distances([p for p, d in home.items() if d == distance])
