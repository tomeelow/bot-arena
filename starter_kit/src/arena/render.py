"""A plain-text board, for debugging in a terminal."""

from arena_engine import GameState, Kind, score

LETTERS = {Kind.WORKER: "w", Kind.SOLDIER: "s", Kind.SCOUT: "x"}
LEGEND = "# wall  $ deposit  C/c Core  W/w worker  S/s soldier  X/x scout  (capitals: seat 0)"


def render(state: GameState) -> str:
    rules = state.rules
    rows = [["."] * rules.width for _ in range(rules.height)]
    for p in state.walls:
        rows[p.y][p.x] = "#"
    for d in state.deposits:
        rows[d.pos.y][d.pos.x] = "$"
    for c in state.cores:
        rows[c.pos.y][c.pos.x] = "C" if c.seat == 0 else "c"
    for u in state.units:
        letter = LETTERS[u.kind]
        rows[u.pos.y][u.pos.x] = letter.upper() if u.seat == 0 else letter

    lines = ["".join(row) for row in rows]
    lines.append(f"turn {state.turn}/{rules.max_turns}")
    for seat in (0, 1):
        counts = ", ".join(
            f"{sum(u.seat == seat and u.kind is k for u in state.units)} {k.value}s" for k in Kind
        )
        lines.append(
            f"seat {seat}: Core {state.cores[seat].hp} hp, bank {state.banks[seat]}, {counts}, "
            f"score {score(state, seat)}"
        )
    lines.append(LEGEND)
    return "\n".join(lines)
