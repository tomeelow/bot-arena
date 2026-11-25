"""Record the golden games in engine/tests/golden/.

Regenerate only after a deliberate rule change, with ENGINE_VERSION bumped in the same
change: these files are what proves old replays still mean the same thing.

    uv run python engine/tests/make_golden.py
"""

import gzip
import json
import logging

from engine_support import RandomBot, play
from golden_check import GOLDEN_DIR, replay_hashes

from arena_engine import ENGINE_VERSION, order_to_plain

log = logging.getLogger(__name__)

# (name, map seed, seat 0 bot seed, seat 1 bot seed)
GAMES = [
    ("core-destroyed", 1, 10, 20),
    ("turn-limit", 4, 10, 20),
    ("crowded", 42, 7, 8),
]


def main() -> None:
    GOLDEN_DIR.mkdir(exist_ok=True)
    for name, seed, a, b in GAMES:
        game = play((RandomBot(a), RandomBot(b)), seed, turns=400)
        fixture = {
            "name": name,
            "engine_version": ENGINE_VERSION,
            "seed": seed,
            "orders": [
                [[order_to_plain(o) for o in side] for side in turn] for turn in game.orders
            ],
        }
        fixture["hashes"] = replay_hashes(fixture)
        encoded = json.dumps(fixture, separators=(",", ":")).encode()
        (GOLDEN_DIR / f"{name}.json.gz").write_bytes(gzip.compress(encoded, mtime=0))
        end = game.states[-1].outcome
        log.info("%s: %d turns, %s, %d KiB raw", name, len(game.orders), end, len(encoded) // 1024)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main()
