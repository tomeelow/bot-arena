"""PPO against a league: the scripted bots, past checkpoints and the current policy.

    cd rl
    uv run python -m arena_rl.train config.toml runs/stage1    # stage 1, from scratch
    uv run python -m arena_rl.train finetune.toml runs/stage2  # stage 2, from stage 1

Everything comes from the config and its seed: game seeds, opponents, minibatches and the
bots' own sampling (each bot's rng is seeded from its game, as in the harness). A run
repeated on the same machine and numpy build gives the same weights; tests/test_train.py
checks this on a short run.

Progress is measured against the fixed scripted baselines on fixed seed pairs, never by
self-play: see `progress.jsonl` in the run directory.
"""

import json
import logging
import shutil
import sys
import time
import tomllib
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from arena.builtin import builtin_factory
from arena.tournament import wilson

from . import ppo
from .boss import BossBot, Decision, Layer, Net
from .env import play

log = logging.getLogger("arena_rl.train")
TRAIN_SEEDS = (1_000_000, 2**31 - 1)  # evaluation uses seeds below this range, never above

type Opponent = str | dict[str, Layer]  # a built-in's name, or a policy's weights


@dataclass(frozen=True)
class Job:
    learner: dict[str, Layer]
    opponent: Opponent
    seed: int
    seat: int


def rollout(job: Job) -> tuple[list[Decision], float, bool]:
    """One game; the learner's decisions and its result: 1 win, 0 draw, -1 loss."""
    me = BossBot(Net(job.learner))
    me.trace = []
    other = (
        builtin_factory(job.opponent)()
        if isinstance(job.opponent, str)
        else BossBot(Net(job.opponent))
    )
    bots = (me, other) if job.seat == 0 else (other, me)
    result, _ = play(bots, job.seed)
    reward = 0.0 if result.winner is None else (1.0 if result.winner == job.seat else -1.0)
    return me.trace, reward, result.reason == "core_destroyed"


class League:
    """Who the learner plays: a scripted bot, a past checkpoint, or its current self."""

    def __init__(self, cfg: dict[str, Any], rng: np.random.Generator) -> None:
        self.cfg, self.rng = cfg, rng
        self.scripted = list(cfg["scripted"])
        weights = np.array([cfg["scripted"][k] for k in self.scripted], dtype=float)
        self.weights = weights / weights.sum()
        self.past: list[dict[str, Layer]] = []

    def pick(self, current: dict[str, Layer]) -> Opponent:
        r = self.rng.random()
        if r < self.cfg["scripted_share"] or not self.past:
            return self.scripted[int(self.rng.choice(len(self.scripted), p=self.weights))]
        if r < self.cfg["scripted_share"] + self.cfg["past_share"]:
            return self.past[int(self.rng.integers(len(self.past)))]
        return current


def evaluate(
    pool: ProcessPoolExecutor, layers: dict[str, Layer], baselines: list[str], seed_pairs: int
) -> dict[str, dict[str, float]]:
    """Score against each baseline over seeds 0..seed_pairs-1, each from both seats."""
    jobs = [
        Job(layers, b, seed, seat)
        for b in baselines
        for seed in range(seed_pairs)
        for seat in (0, 1)
    ]
    rewards = [r for _, r, _ in pool.map(rollout, jobs, chunksize=4)]
    out: dict[str, dict[str, float]] = {}
    per = 2 * seed_pairs
    for i, b in enumerate(baselines):
        rs = rewards[i * per : (i + 1) * per]
        points = sum((r + 1) / 2 for r in rs)
        lo, hi = wilson(points, per)
        out[b] = {"score": points / per, "lo": lo, "hi": hi}
    return out


def train(cfg: dict[str, Any], out: Path) -> ppo.Params:
    t, lg, ev = cfg["train"], cfg["league"], cfg["eval"]
    rng = np.random.default_rng(t["seed"])
    params = ppo.init(t["hidden"], rng)
    if "init" in t:  # continue from an earlier run's checkpoint
        with np.load(t["init"]) as f:
            params = {k: f[k] for k in params}
    opt = ppo.Adam(params, t["lr"], t["max_grad_norm"])
    league = League(lg, rng)
    coefs = ppo.Coefs(t["clip"], t["value_coef"], t["entropy_coef"])
    baselines = list(lg["scripted"])
    (out / "checkpoints").mkdir(parents=True, exist_ok=True)
    progress = (out / "progress.jsonl").open("a")
    started = time.monotonic()
    steps = 0
    with ProcessPoolExecutor(t["jobs"]) as pool:
        for update in range(1, t["updates"] + 1):
            layers = ppo.to_layers(params)
            jobs = [
                Job(layers, league.pick(layers), int(rng.integers(*TRAIN_SEEDS)), int(seat))
                for seat in rng.integers(0, 2, t["games_per_update"])
            ]
            games = list(pool.map(rollout, jobs, chunksize=2))
            batch, record = _batch(params, games, t)
            steps += len(batch.x)
            stats = _update(params, opt, batch, coefs, t, rng)
            if update % lg["snapshot_every"] == 0:
                league.past.append(ppo.to_layers(params))
            line: dict[str, Any] = {
                "update": update,
                "decisions": steps,
                "wall_s": round(time.monotonic() - started, 1),
                "train_score": record,
                **stats,
            }
            if update % ev["every"] == 0 or update == t["updates"]:
                np.savez(out / "checkpoints" / f"{update:05d}.npz", allow_pickle=False, **params)
                line["eval"] = evaluate(pool, ppo.to_layers(params), baselines, ev["seed_pairs"])
            progress.write(json.dumps(line) + "\n")
            progress.flush()
            log.info("%s", json.dumps(line))
    np.savez(out / "final.npz", allow_pickle=False, **params)
    return params


def _batch(
    params: ppo.Params, games: list[tuple[list[Decision], float, bool]], t: dict[str, Any]
) -> tuple[ppo.Batch, float]:
    xs, builds, stances, advs, rets = [], [], [], [], []
    for trace, reward, _ in games:
        if not trace:
            continue
        x = np.array([d[0] for d in trace])
        values = ppo.forward(params, x).value
        adv = ppo.gae(values, reward, t["gamma"], t["lam"])
        xs.append(x)
        builds += [d[1] for d in trace]
        stances += [d[2] for d in trace]
        advs.append(adv)
        rets.append(adv + values)
    x = np.concatenate(xs)
    build, stance = np.array(builds), np.array(stances)
    old_logp = ppo.log_prob(ppo.forward(params, x), build, stance)
    adv = np.concatenate(advs)
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)
    record = float(np.mean([(r + 1) / 2 for _, r, _ in games]))
    return ppo.Batch(x, build, stance, old_logp, adv, np.concatenate(rets)), record


def _update(
    params: ppo.Params,
    opt: ppo.Adam,
    b: ppo.Batch,
    coefs: ppo.Coefs,
    t: dict[str, Any],
    rng: np.random.Generator,
) -> dict[str, float]:
    stats: dict[str, float] = {}
    for _ in range(t["epochs"]):
        order = rng.permutation(len(b.x))
        for start in range(0, len(order), t["minibatch"]):
            i = order[start : start + t["minibatch"]]
            mb = ppo.Batch(
                b.x[i], b.build[i], b.stance[i], b.old_logp[i], b.advantage[i], b.returns[i]
            )
            _, grads, stats = ppo.loss_and_grads(params, mb, coefs)
            opt.step(params, grads)
    return stats


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    config, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy(config, out / "config.toml")
    cfg = tomllib.loads(config.read_text())
    if "init" in cfg["train"]:  # relative to the config file
        cfg["train"]["init"] = str(config.parent / cfg["train"]["init"])
    train(cfg, out)


if __name__ == "__main__":
    main()
