"""Turn resolution (GAME_RULES.md §4-§7). Nothing here may depend on seat order."""

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import replace

from .geometry import adjacent, dir_to_frame, in_bounds, step_pos, to_frame
from .model import (
    UNIT_STATS,
    Attack,
    Core,
    Deposit,
    EndReason,
    Event,
    GameState,
    InvalidOrder,
    Kind,
    Mine,
    Move,
    Order,
    Outcome,
    Pos,
    Spawn,
    SpawnBlocked,
    StepResult,
    Unit,
    UnitLost,
    UnitOrder,
    Unload,
)

type Key = tuple[int, int]  # (seat, unit id)
SEATS = (0, 1)


def step(state: GameState, orders: Mapping[int, Sequence[Order]]) -> StepResult:
    """Resolve one turn. `orders[seat]` is in that seat's frame; a missing seat holds still."""
    if state.outcome is not None:
        raise ValueError("the game is over")
    events: tuple[list[Event], list[Event]] = ([], [])
    unit_orders: dict[Key, UnitOrder] = {}
    spawns: dict[int, Spawn] = {}
    for seat in SEATS:
        mine, spawn = _validate(state, seat, orders.get(seat, ()), events[seat])
        unit_orders |= {(seat, uid): o for uid, o in mine.items()}
        if spawn is not None:
            spawns[seat] = spawn

    units = {(u.seat, u.id): u for u in state.units}
    units, cores, lost = _attacks(state, units, unit_orders, events)
    units = _moves(state, units, unit_orders)
    units, deposits, banks = _mining(state, units, unit_orders)
    units, banks, spent, next_id = _spawns(state, units, cores, banks, spawns, events)

    new = replace(
        state,
        turn=state.turn + 1,
        deposits=deposits,
        cores=cores,
        units=tuple(units[k] for k in sorted(units)),
        banks=banks,
        next_id=next_id,
        spent=spent,
        lost=state.lost + lost,
    )
    new = replace(new, outcome=_outcome(new))
    return StepResult(new, (tuple(events[0]), tuple(events[1])))


def _validate(
    state: GameState, seat: int, orders: Sequence[Order], events: list[Event]
) -> tuple[dict[int, UnitOrder], Spawn | None]:
    """Keep the valid orders, converted to the absolute frame; report the rest."""
    rules = state.rules
    own = {u.id: u for u in state.units if u.seat == seat}
    core = state.cores[seat]
    blocked = _blocked_cells(state)
    deposits = {d.pos: d.amount for d in state.deposits}
    occupant = {u.pos: u for u in state.units}
    per_unit = Counter(o.unit for o in orders if not isinstance(o, Spawn))
    spawn_count = sum(isinstance(o, Spawn) for o in orders)

    valid: dict[int, UnitOrder] = {}
    spawn: Spawn | None = None

    def reject(order: Order, reason: str) -> None:
        events.append(InvalidOrder(order, reason))

    for order in orders:
        if isinstance(order, Spawn):
            d = dir_to_frame(order.dir, seat)
            target = step_pos(core.pos, d)
            cost = UNIT_STATS[order.kind].cost
            if spawn_count > 1:
                reject(order, "more than one spawn this turn")
            elif not in_bounds(target, rules) or target in blocked:
                reject(order, "cannot spawn onto that cell")
            elif state.banks[seat] < cost:
                reject(order, "not enough crystals")
            elif len(own) >= rules.max_units:
                reject(order, "unit limit reached")
            else:
                spawn = Spawn(order.kind, d)
            continue

        unit = own.get(order.unit)
        if unit is None:
            reject(order, "no such unit")
            continue
        if per_unit[order.unit] > 1:
            reject(order, "more than one order for this unit")
            continue
        stats = UNIT_STATS[unit.kind]
        if isinstance(order, Unload):
            if unit.kind is not Kind.WORKER:
                reject(order, "only workers unload")
            elif unit.cargo == 0:
                reject(order, "nothing to unload")
            elif not adjacent(unit.pos, core.pos):
                reject(order, "not next to your core")
            else:
                valid[unit.id] = order
            continue

        d = dir_to_frame(order.dir, seat)
        target = step_pos(unit.pos, d)
        match order:
            case Move():
                if not in_bounds(target, rules) or target in blocked:
                    reject(order, "cannot move onto that cell")
                else:
                    valid[unit.id] = Move(unit.id, d)
            case Mine():
                if unit.kind is not Kind.WORKER:
                    reject(order, "only workers mine")
                elif deposits.get(target, 0) == 0:
                    reject(order, "no crystals there")
                elif unit.cargo >= stats.carry:
                    reject(order, "cargo is full")
                else:
                    valid[unit.id] = Mine(unit.id, d)
            case Attack():
                target_unit = occupant.get(target)
                enemy_core = state.cores[1 - seat]
                hits_unit = target_unit is not None and target_unit.seat != seat
                if stats.attack == 0:
                    reject(order, "this unit cannot attack")
                elif not hits_unit and target != enemy_core.pos:
                    reject(order, "no enemy there")
                else:
                    valid[unit.id] = Attack(unit.id, d)
    return valid, spawn


def _blocked_cells(state: GameState) -> set[Pos]:
    """Cells no unit may ever stand on: walls, deposits and Cores."""
    return set(state.walls) | {d.pos for d in state.deposits} | {c.pos for c in state.cores}


def _attacks(
    state: GameState,
    units: dict[Key, Unit],
    orders: Mapping[Key, UnitOrder],
    events: tuple[list[Event], list[Event]],
) -> tuple[dict[Key, Unit], tuple[Core, Core], int]:
    damage: Counter[Pos] = Counter()
    for key, order in orders.items():
        if isinstance(order, Attack):
            unit = units[key]
            damage[step_pos(unit.pos, order.dir)] += UNIT_STATS[unit.kind].attack

    survivors: dict[Key, Unit] = {}
    lost = 0
    for key, unit in units.items():
        hp = unit.hp - damage[unit.pos]
        if hp > 0:
            survivors[key] = replace(unit, hp=hp)
        else:
            lost += unit.cargo
            pos = to_frame(unit.pos, unit.seat, state.rules)
            events[unit.seat].append(UnitLost(unit.id, pos))
    c0, c1 = (replace(c, hp=max(0, c.hp - damage[c.pos])) for c in state.cores)
    return survivors, (c0, c1), lost


def _moves(
    state: GameState, units: dict[Key, Unit], orders: Mapping[Key, UnitOrder]
) -> dict[Key, Unit]:
    targets = {
        key: step_pos(units[key].pos, o.dir)
        for key, o in orders.items()
        if isinstance(o, Move) and key in units
    }
    at = {u.pos: key for key, u in units.items()}
    contested = Counter(targets.values())

    def swapping(key: Key, target: Pos) -> bool:
        other = at.get(target)
        return other is not None and targets.get(other) == units[key].pos

    stuck = {k for k, t in targets.items() if contested[t] > 1 or swapping(k, t)}

    # A mover is stuck if its target holds a unit that isn't leaving. Blocking only ever
    # grows, so the fixpoint is the same in any iteration order.
    changed = True
    while changed:
        changed = False
        for key, target in targets.items():
            occupant = at.get(target)
            if key in stuck or occupant is None:
                continue
            if occupant not in targets or occupant in stuck:
                stuck.add(key)
                changed = True

    return {
        key: replace(u, pos=targets[key]) if key in targets and key not in stuck else u
        for key, u in units.items()
    }


def _mining(
    state: GameState, units: dict[Key, Unit], orders: Mapping[Key, UnitOrder]
) -> tuple[dict[Key, Unit], tuple[Deposit, ...], tuple[int, int]]:
    requests: dict[Pos, list[tuple[Key, int]]] = {}
    banks = list(state.banks)
    units = dict(units)
    for key, order in orders.items():
        unit = units.get(key)
        if unit is None:
            continue
        if isinstance(order, Mine):
            want = min(state.rules.mine_rate, UNIT_STATS[unit.kind].carry - unit.cargo)
            requests.setdefault(step_pos(unit.pos, order.dir), []).append((key, want))
        elif isinstance(order, Unload):
            banks[unit.seat] += unit.cargo
            units[key] = replace(unit, cargo=0)

    deposits: list[Deposit] = []
    for deposit in state.deposits:
        claims = requests.get(deposit.pos, [])
        total = sum(want for _, want in claims)
        share = deposit.amount // len(claims) if claims else 0
        taken = 0
        for key, want in claims:
            got = want if total <= deposit.amount else min(want, share)
            units[key] = replace(units[key], cargo=units[key].cargo + got)
            taken += got
        deposits.append(replace(deposit, amount=deposit.amount - taken))
    return units, tuple(deposits), (banks[0], banks[1])


def _spawns(
    state: GameState,
    units: dict[Key, Unit],
    cores: tuple[Core, Core],
    banks: tuple[int, int],
    spawns: Mapping[int, Spawn],
    events: tuple[list[Event], list[Event]],
) -> tuple[dict[Key, Unit], tuple[int, int], tuple[int, int], tuple[int, int]]:
    new_banks, spent, next_id = list(banks), list(state.spent), list(state.next_id)
    occupied = {u.pos for u in units.values()}
    targets = {seat: step_pos(cores[seat].pos, s.dir) for seat, s in spawns.items()}
    contested = Counter(targets.values())
    units = dict(units)
    for seat, order in spawns.items():
        target = targets[seat]
        if cores[seat].hp <= 0:
            continue
        if target in occupied or contested[target] > 1:
            pos = to_frame(target, seat, state.rules)
            events[seat].append(SpawnBlocked(order.kind, pos))
            continue
        stats = UNIT_STATS[order.kind]
        uid = next_id[seat]
        units[(seat, uid)] = Unit(seat, uid, order.kind, target, stats.hp)
        new_banks[seat] -= stats.cost
        spent[seat] += stats.cost
        next_id[seat] += 1
    return (
        units,
        (new_banks[0], new_banks[1]),
        (spent[0], spent[1]),
        (next_id[0], next_id[1]),
    )


def score(state: GameState, seat: int) -> int:
    """Bank + carried crystals + spawn cost of every living unit (GAME_RULES.md §7)."""
    own = [u for u in state.units if u.seat == seat]
    return state.banks[seat] + sum(u.cargo + UNIT_STATS[u.kind].cost for u in own)


def _outcome(state: GameState) -> Outcome | None:
    dead = [c.hp <= 0 for c in state.cores]
    if all(dead):
        return Outcome(None, EndReason.CORE_DESTROYED, state.turn)
    if any(dead):
        return Outcome(dead.index(False), EndReason.CORE_DESTROYED, state.turn)
    if state.turn >= state.rules.max_turns:
        s0, s1 = score(state, 0), score(state, 1)
        winner = None if s0 == s1 else (0 if s0 > s1 else 1)
        return Outcome(winner, EndReason.TURN_LIMIT, state.turn)
    return None
