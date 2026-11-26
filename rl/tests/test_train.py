"""Training is reproducible from its config and seed."""

import tomllib
from pathlib import Path

import numpy as np
from arena_rl.train import train

CONFIG = tomllib.loads((Path(__file__).parents[1] / "config.toml").read_text())


def test_the_same_config_and_seed_train_the_same_weights(tmp_path):
    cfg = {**CONFIG, "train": {**CONFIG["train"], "updates": 2, "games_per_update": 4,
                               "jobs": 2, "minibatch": 64}}  # fmt: skip
    cfg["league"] = {**CONFIG["league"], "snapshot_every": 1}
    cfg["eval"] = {"every": 2, "seed_pairs": 1}
    a, b = train(cfg, tmp_path / "a"), train(cfg, tmp_path / "b")
    assert all(np.array_equal(a[k], b[k]) for k in a)
    assert (tmp_path / "a/progress.jsonl").read_text().count("\n") == 2
