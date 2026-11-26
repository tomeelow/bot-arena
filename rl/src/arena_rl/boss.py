"""The arena's boss: a learned policy makes the strategic calls and shared tactics move the units.

Every few turns a small neural network looks at what the bot has seen so far and picks two
things: what the Core builds, and what the soldiers do (hold a ring at home, march on the
enemy Core, or hunt the enemy units it has seen). Workers mine, and soldiers fight what is
next to them, with the same tactics as the built-in bots (arena.builtin.tactics).

This file is the whole bot. `arena_rl.export` appends the trained weights to its source, and
the result is uploaded like anyone else's bot: one .py file, the same jail and the same
limits. It imports only the starter kit and the standard library, so it needs nothing
installed in the jail beyond what every bot gets.
"""

import math
from collections.abc import Callable, Sequence

from arena import UNIT_STATS, Bot, Grid, Kind, Observation, Order, Pos, UnitLost, dist2
from arena.builtin.tactics import Context, Economy, Plan, guard, guard_post, march

DECIDE_EVERY = 4  # turns between decisions; the tactics act every turn
BUILDS: tuple[Kind | None, ...] = (None, Kind.WORKER, Kind.SOLDIER, Kind.SCOUT)
STANCES = ("defend", "attack", "hunt")
NEAR_CORE2 = 64  # "near my Core": within 8 cells
CLOSING2 = 196  # "closing in": within 14 cells
PEAK_WINDOW = 40  # turns over which the largest enemy army seen is remembered
UNSEEN_DEPOSIT = 225  # a deposit we haven't seen yet is assumed average (150-300)

type Matrix = list[list[float]]
type Layer = tuple[Matrix, list[float]]


class Net:
    """A two-layer tanh MLP with three heads: build logits, stance logits and a value.
    Pure Python, so the bot needs no numpy. `arena_rl.ppo` trains the same network in
    numpy, and a test checks the two give the same outputs."""

    def __init__(self, weights: dict[str, Layer]) -> None:
        self.trunk = [weights["h1"], weights["h2"]]
        self.heads = [weights["build"], weights["stance"], weights["value"]]

    def __call__(self, x: Sequence[float]) -> tuple[list[float], list[float], float]:
        h = list(x)
        for layer in self.trunk:
            h = [math.tanh(v) for v in _affine(h, layer)]
        build, stance, value = (_affine(h, head) for head in self.heads)
        return build, stance, value[0]


def _affine(x: list[float], layer: Layer) -> list[float]:
    w, b = layer
    out = list(b)
    for xi, row in zip(x, w, strict=True):
        if xi:
            for j, wij in enumerate(row):
                out[j] += xi * wij
    return out


def softmax(logits: Sequence[float]) -> list[float]:
    top = max(logits)
    e = [math.exp(v - top) for v in logits]
    total = sum(e)
    return [v / total for v in e]


type Decision = tuple[list[float], int, int]  # features, build index, stance index


class BossBot(Bot):
    """`net` and `trace` are for training: by default the bot plays the shipped weights, and
    with a trace list it records every decision it makes."""

    def __init__(
        self, net: Callable[[Sequence[float]], tuple[list[float], list[float], float]] | None = None
    ) -> None:
        self.net = net or Net(WEIGHTS)
        self.trace: list[Decision] | None = None

    def setup(self) -> None:
        self.ctx = Context(self.map, self.rules, Grid(self.map), self.rng)
        self.economy = Economy(self.ctx)
        self.post = guard_post(self.ctx, 3)
        self.to_enemy = self.ctx.grid.distances([self.map.enemy_core])
        self.build, self.stance = 0, 0
        self.enemy_core_hp = self.rules.core_hp
        self.soldier_sightings: list[tuple[int, int]] = []  # (turn, enemy soldiers in view)
        self.last_soldier_turn = -PEAK_WINDOW
        self.last_seen: list[Pos] = []
        self.losses = 0
        # What tells a turtle from a rush: soldiers parked at their Core, or crossing over.
        self.most_at_their_core = 0
        self.most_in_my_half = 0
        self.first_in_my_half = self.rules.max_turns

    def act(self, obs: Observation) -> list[Order]:
        self._remember(obs)
        if obs.turn % DECIDE_EVERY == 0:
            x = self.features(obs)
            build, stance, _ = self.net(x)
            self.build = _sample(softmax(build), self.rng.random())
            self.stance = _sample(softmax(stance), self.rng.random())
            if self.trace is not None:
                self.trace.append((x, self.build, self.stance))

        plan = Plan(obs, self.ctx)
        self.economy.plan(plan)
        march(plan, plan.of_kind(Kind.SCOUT), self.to_enemy)
        soldiers = plan.of_kind(Kind.SOLDIER)
        match STANCES[self.stance]:
            case "defend":
                guard(plan, soldiers, self.post, NEAR_CORE2)
            case "attack":
                march(plan, soldiers, self.to_enemy)
            case _:
                targets = [e.pos for e in obs.enemies] or self.last_seen
                field = self.ctx.grid.distances(targets) if targets else self.to_enemy
                march(plan, soldiers, field)
        if (kind := BUILDS[self.build]) is not None:
            plan.spawn(kind)
        return plan.orders

    def _remember(self, obs: Observation) -> None:
        self.losses += sum(isinstance(e, UnitLost) for e in self.events)
        if obs.enemy_core_hp is not None:
            self.enemy_core_hp = obs.enemy_core_hp
        if obs.enemies:
            self.last_seen = [e.pos for e in obs.enemies]
        enemy_soldiers = [e.pos for e in obs.enemies if e.kind is Kind.SOLDIER]
        core, enemy_core = self.map.my_core, self.map.enemy_core
        at_their_core = sum(dist2(p, enemy_core) <= NEAR_CORE2 for p in enemy_soldiers)
        in_my_half = sum(dist2(p, core) < dist2(p, enemy_core) for p in enemy_soldiers)
        self.most_at_their_core = max(self.most_at_their_core, at_their_core)
        self.most_in_my_half = max(self.most_in_my_half, in_my_half)
        if in_my_half:
            self.first_in_my_half = min(self.first_in_my_half, obs.turn)
        soldiers = len(enemy_soldiers)
        if soldiers:
            self.last_soldier_turn = obs.turn
            self.soldier_sightings.append((obs.turn, soldiers))
        self.soldier_sightings = [
            s for s in self.soldier_sightings if obs.turn - s[0] < PEAK_WINDOW
        ]

    def features(self, obs: Observation) -> list[float]:
        """What the network sees: the observation and this bot's memory of earlier ones,
        each scaled to about 0-1."""
        core, enemy_core = self.map.my_core, self.map.enemy_core
        mine = {k: [u for u in obs.units if u.kind is k] for k in Kind}
        seen = {k: [e for e in obs.enemies if e.kind is k] for k in Kind}
        workers, soldiers = mine[Kind.WORKER], mine[Kind.SOLDIER]
        sites = self.map.deposit_sites
        crystals = sum(self.economy.known.get(s, UNSEEN_DEPOSIT) for s in sites)
        score = obs.bank + sum(w.cargo for w in workers)
        score += sum(UNIT_STATS[u.kind].cost for u in obs.units)
        return [
            obs.turn / self.rules.max_turns,
            min(obs.bank, 400) / 400,
            obs.core_hp / self.rules.core_hp,
            len(workers) / 10,
            len(soldiers) / 10,
            len(mine[Kind.SCOUT]) / 5,
            sum(s.hp for s in soldiers) / 300,
            sum(w.cargo > 0 for w in workers) / max(len(workers), 1),
            len(seen[Kind.WORKER]) / 10,
            len(seen[Kind.SOLDIER]) / 10,
            len(seen[Kind.SCOUT]) / 5,
            sum(dist2(e.pos, core) <= NEAR_CORE2 for e in seen[Kind.SOLDIER]) / 5,
            sum(dist2(e.pos, core) <= CLOSING2 for e in obs.enemies) / 5,
            self.enemy_core_hp / self.rules.core_hp,
            max((n for _, n in self.soldier_sightings), default=0) / 10,
            min(obs.turn - self.last_soldier_turn, 100) / 100,
            sum(dist2(s.pos, enemy_core) <= NEAR_CORE2 for s in soldiers) / 10,
            crystals / (UNSEEN_DEPOSIT * len(sites)) if sites else 0.0,
            self.losses / 20,
            score / 1000,
            self.most_at_their_core / 10,
            self.most_in_my_half / 10,
            self.first_in_my_half / self.rules.max_turns,
            *(float(i == self.build) for i in range(len(BUILDS))),
            *(float(i == self.stance) for i in range(len(STANCES))),
        ]


def _sample(probs: list[float], u: float) -> int:
    """Index drawn from `probs` by the uniform number `u`: the bot's own seeded rng, so a
    match replays exactly."""
    total = 0.0
    for i, p in enumerate(probs):
        total += p
        if u < total:
            return i
    return len(probs) - 1


N_FEATURES = 23 + len(BUILDS) + len(STANCES)

# Filled in by arena_rl.export. Without weights the bot fails its smoke match on upload.
WEIGHTS: dict[str, Layer] = {}
