"""What the viewer draws (Phase 7): a header with the map, then one frame per turn.

Live matches and replays use the same encoding; a live match is just a replay that is still
being written (`live/<match_id>.jsonl`, appended by the worker). A frame is a full snapshot:
gzip takes out the repetition, so deltas would only add code.
"""

import base64
from typing import Any

from arena.runner import Result
from arena_engine import GameState, visible_cells

KIND = {"worker": "w", "soldier": "s", "scout": "x"}


def header(state: GameState, players: list[dict[str, Any]]) -> dict[str, Any]:
    rules = state.rules
    return {
        "type": "header",
        "width": rules.width,
        "height": rules.height,
        "max_turns": rules.max_turns,
        "walls": sorted([p.x, p.y] for p in state.walls),
        "cores": [[c.pos.x, c.pos.y] for c in state.cores],
        "players": players,
    }


def frame(state: GameState) -> dict[str, Any]:
    return {
        "type": "frame",
        "turn": state.turn,
        "units": [[u.seat, u.id, KIND[u.kind.value], u.pos.x, u.pos.y, u.hp, u.cargo]
                  for u in state.units],
        "cores": [c.hp for c in state.cores],
        "banks": list(state.banks),
        "deposits": [[d.pos.x, d.pos.y, d.amount] for d in state.deposits],
        "visible": [_mask(state, seat) for seat in (0, 1)],
    }  # fmt: skip


def end(result: Result) -> dict[str, Any]:
    return {"type": "end", "winner": result.winner, "reason": result.reason, "turns": result.turns}


def _mask(state: GameState, seat: int) -> str:
    """Which cells `seat` saw, as a base64 bitmap in row-major order: lets the viewer show
    exactly what each bot knew."""
    width = state.rules.width
    bits = bytearray((width * state.rules.height + 7) // 8)
    for p in visible_cells(state, seat):
        i = p.y * width + p.x
        bits[i // 8] |= 1 << (i % 8)
    return base64.b64encode(bytes(bits)).decode()
