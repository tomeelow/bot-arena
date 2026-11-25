"""Pathfinding over the static map. Walls, deposits and Cores never move, so a `Grid` can be
built once in `setup` and reused every turn."""

from collections.abc import Iterable

from arena_engine import Dir, MapInfo, Pos
from arena_engine.geometry import DIRS, step_pos


class Grid:
    def __init__(self, info: MapInfo) -> None:
        self.width = info.width
        self.height = info.height
        self.blocked = {*info.walls, *info.deposit_sites, info.my_core, info.enemy_core}

    def in_bounds(self, p: Pos) -> bool:
        return 0 <= p.x < self.width and 0 <= p.y < self.height

    def passable(self, p: Pos) -> bool:
        return self.in_bounds(p) and p not in self.blocked

    def open_neighbours(self, p: Pos) -> list[tuple[Dir, Pos]]:
        return [(d, n) for d in DIRS if self.passable(n := step_pos(p, d))]

    def distances(self, targets: Iterable[Pos]) -> dict[Pos, int]:
        """Steps from each reachable open cell to the nearest target. A blocked target (a
        deposit or a Core) counts as reached from any open cell next to it."""
        start: list[Pos] = []
        for t in targets:
            start += [t] if self.passable(t) else [n for _, n in self.open_neighbours(t)]
        dist = dict.fromkeys(start, 0)
        frontier = list(dist)
        while frontier:
            nxt: list[Pos] = []
            for p in frontier:
                for _, n in self.open_neighbours(p):
                    if n not in dist:
                        dist[n] = dist[p] + 1
                        nxt.append(n)
            frontier = nxt
        return dist

    def step_toward(self, p: Pos, dist: dict[Pos, int], avoid: Iterable[Pos] = ()) -> Dir | None:
        """The first step downhill in `dist` that isn't in `avoid`, or None if there is none."""
        here = dist.get(p)
        skip = set(avoid)
        best: tuple[int, Dir] | None = None
        for d, n in self.open_neighbours(p):
            if n in skip or n not in dist or (here is not None and dist[n] >= here):
                continue
            if best is None or dist[n] < best[0]:
                best = (dist[n], d)
        return best[1] if best else None
