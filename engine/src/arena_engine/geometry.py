"""Grid geometry and the seat-relative frame (seat 1 sees the map rotated 180°)."""

from .model import Dir, Pos, Rules

OFFSET: dict[Dir, tuple[int, int]] = {
    Dir.N: (0, -1),
    Dir.E: (1, 0),
    Dir.S: (0, 1),
    Dir.W: (-1, 0),
}
OPPOSITE: dict[Dir, Dir] = {Dir.N: Dir.S, Dir.S: Dir.N, Dir.E: Dir.W, Dir.W: Dir.E}
DIRS: tuple[Dir, ...] = (Dir.N, Dir.E, Dir.S, Dir.W)


def step_pos(pos: Pos, d: Dir) -> Pos:
    dx, dy = OFFSET[d]
    return Pos(pos.x + dx, pos.y + dy)


def in_bounds(pos: Pos, rules: Rules) -> bool:
    return 0 <= pos.x < rules.width and 0 <= pos.y < rules.height


def dist2(a: Pos, b: Pos) -> int:
    return (a.x - b.x) ** 2 + (a.y - b.y) ** 2


def adjacent(a: Pos, b: Pos) -> bool:
    return abs(a.x - b.x) + abs(a.y - b.y) == 1


def mirror(pos: Pos, rules: Rules) -> Pos:
    return Pos(rules.width - 1 - pos.x, rules.height - 1 - pos.y)


def to_frame(pos: Pos, seat: int, rules: Rules) -> Pos:
    """Absolute position to `seat`'s frame. The rotation is its own inverse."""
    return pos if seat == 0 else mirror(pos, rules)


def dir_to_frame(d: Dir, seat: int) -> Dir:
    """Absolute direction to `seat`'s frame, and back: also its own inverse."""
    return d if seat == 0 else OPPOSITE[d]
