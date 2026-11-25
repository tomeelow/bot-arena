"""Seeded, 180°-symmetric map generation (GAME_RULES.md §2)."""

from random import Random

from .geometry import DIRS, dist2, in_bounds, mirror, step_pos
from .model import UNIT_STATS, Core, Deposit, Dir, GameState, Kind, Pos, Rules, Unit

MAX_ATTEMPTS = 100
START_WORKER_DIRS = (Dir.E, Dir.S)  # seat 0's frame; seat 1 gets the mirror image


def new_game(rules: Rules, seed: int) -> GameState:
    if rules.width < 16 or rules.height < 16:
        raise ValueError("generated maps need at least 16 x 16 cells")
    rng = Random(seed)
    for _ in range(MAX_ATTEMPTS):
        state = _attempt(rules, rng)
        if state is not None:
            return state
    raise RuntimeError(f"no valid map for seed {seed} in {MAX_ATTEMPTS} attempts")


def _attempt(rules: Rules, rng: Random) -> GameState | None:
    # Generate seat 0's half, then mirror it. Lists keep every draw in a fixed order.
    half = [
        p
        for y in range(rules.height)
        for x in range(rules.width)
        if (p := Pos(x, y)) < mirror(p, rules)
    ]
    core = Pos(rng.randrange(3, 8), rng.randrange(3, 8))
    clear = {p for p in half if dist2(p, core) <= rules.core_clear_radius2}
    walls = {p for p in half if p not in clear and rng.randrange(100) < rules.wall_percent}

    sites: list[Pos] = []
    home = [
        p
        for p in half
        if p not in walls
        and rules.home_deposit_min_dist2 <= dist2(p, core) <= rules.home_deposit_max_dist2
    ]
    field = [
        p
        for p in half
        if p not in walls and p not in clear and dist2(p, core) > rules.home_deposit_max_dist2
    ]
    for pool, count in ((home, rules.home_deposits), (field, rules.field_deposits)):
        for _ in range(count):
            site = rng.choice(pool)
            pool.remove(site)
            sites.append(site)
    amounts = [
        10 * rng.randrange(rules.deposit_min // 10, rules.deposit_max // 10 + 1) for _ in sites
    ]

    deposits = [Deposit(p, a) for p, a in zip(sites, amounts, strict=True)]
    deposits += [Deposit(mirror(d.pos, rules), d.amount) for d in deposits]
    walls |= {mirror(p, rules) for p in walls}
    cores = (Core(0, core, rules.core_hp), Core(1, mirror(core, rules), rules.core_hp))
    blocked = walls | {d.pos for d in deposits} | {c.pos for c in cores}

    reached = _flood(cores[0].pos, blocked, rules)
    reachable = [cores[1].pos] + [d.pos for d in deposits]
    if not all(_touches(p, reached, rules) for p in reachable):
        return None
    walls |= {
        p
        for y in range(rules.height)
        for x in range(rules.width)
        if (p := Pos(x, y)) not in blocked and p not in reached
    }

    stats = UNIT_STATS[Kind.WORKER]
    units = [
        Unit(0, i, Kind.WORKER, step_pos(core, d), stats.hp)
        for i, d in enumerate(START_WORKER_DIRS, start=1)
    ]
    units += [Unit(1, u.id, u.kind, mirror(u.pos, rules), u.hp) for u in units]
    first_free_id = len(START_WORKER_DIRS) + 1
    return GameState(
        rules=rules,
        turn=0,
        walls=frozenset(walls),
        deposits=tuple(sorted(deposits, key=lambda d: d.pos)),
        cores=cores,
        units=tuple(sorted(units, key=lambda u: (u.seat, u.id))),
        banks=(rules.start_bank, rules.start_bank),
        next_id=(first_free_id, first_free_id),
        spent=(0, 0),
        lost=0,
    )


def _flood(core: Pos, blocked: set[Pos], rules: Rules) -> set[Pos]:
    """Open cells reachable from the cells next to `core`."""
    frontier = [n for d in DIRS if in_bounds(n := step_pos(core, d), rules) and n not in blocked]
    reached = set(frontier)
    while frontier:
        nxt: list[Pos] = []
        for p in frontier:
            for d in DIRS:
                n = step_pos(p, d)
                if in_bounds(n, rules) and n not in blocked and n not in reached:
                    reached.add(n)
                    nxt.append(n)
        frontier = nxt
    return reached


def _touches(pos: Pos, cells: set[Pos], rules: Rules) -> bool:
    return any(in_bounds(n := step_pos(pos, d), rules) and n in cells for d in DIRS)
