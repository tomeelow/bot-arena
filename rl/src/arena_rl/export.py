"""Write the shipped bot: boss.py's source with the trained weights filled in.

    uv run --project rl python -m arena_rl.export rl/runs/v1/final.npz rl/runs/v1/boss.py

The output is a single .py file that imports only the starter kit, uploaded through the
normal pipeline like any other bot. It holds the weights, so it is never committed: it ships
as a GitHub release asset next to the model card (CLAUDE.md, "never commit model weights").
"""

import hashlib
import sys
from pathlib import Path

import numpy as np

from . import boss, ppo

PLACEHOLDER = "WEIGHTS: dict[str, Layer] = {}\n"


def bundle(params: ppo.Params) -> str:
    source = Path(boss.__file__).read_text()
    assert source.count(PLACEHOLDER) == 1, "boss.py must end with the empty WEIGHTS line"
    return source.replace(PLACEHOLDER, f"WEIGHTS: dict[str, Layer] = {ppo.to_layers(params)!r}\n")


def main() -> None:
    weights, out = Path(sys.argv[1]), Path(sys.argv[2])
    with np.load(weights) as f:
        params = {k: f[k] for k in f.files}
    data = bundle(params).encode()
    out.write_bytes(data)
    sys.stdout.write(f"{out}: {len(data)} bytes, sha256:{hashlib.sha256(data).hexdigest()}\n")


if __name__ == "__main__":
    main()
