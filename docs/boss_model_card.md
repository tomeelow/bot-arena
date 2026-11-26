# Model card: the arena boss

**Bundle:** `boss.py`, 152,108 bytes, `sha256:822c8092ab1fb12932390d549c078efe884b3b905f9a5ef6a4bdc5bdab10af9b` · **Weights:** `final.npz`, `sha256:401986010c8646e9b1f25ea6679e70dd4d4d0e8cec0c5e0a25e978f35d951637` · **Engine version:** 1.0.0 · **Date:** 2026-11-26

The weights are not in the repository. They ship as GitHub release assets next to this card (CLAUDE.md). Ladder rating: not yet published (the boss isn't on the live ladder yet).

## What it is

A bot whose strategy is learned and whose tactics are scripted (ADR-012). Every 4 turns a two-layer MLP (64 tanh units, 6,664 parameters) makes two choices:

- **What the Core builds:** nothing, a worker, a soldier or a scout.
- **What the soldiers do:** *defend* a ring 3 cells from home, *attack* the enemy Core, or *hunt* the enemy units seen last.

Moving, mining and fighting adjacent units use `arena.builtin.tactics`, the same code as the scripted bots. The network sees 30 scaled features, built from the current observation and the bot's memory of earlier ones:

- own economy and army;
- enemies in view, and enemy soldiers near its Core;
- the most enemy soldiers it has seen at their Core or in its own half;
- known crystals left;
- its own last decision.

The bot is one pure-Python file that imports only the starter kit and the standard library. It plays under exactly the rules every bot does: the same observations, the same jail and limits, uploaded through the normal pipeline (`python -m arena_server.ops upload-boss boss.py`).

## Training

| | |
|---|---|
| Algorithm | PPO (clip 0.2, GAE γ 0.99 per decision, λ 0.95, 4 epochs, minibatch 512, Adam 3e-4), numpy with hand-written gradients |
| Reward | the result only: +1 win, 0 draw, −1 loss |
| Stage 1 (`rl/config.toml`) | from scratch, 150 updates × 72 games, entropy 0.01, seed 1 |
| Stage 2 (`rl/finetune.toml`) | from stage 1's last checkpoint, 300 updates × 72 games, seed 2 |
| Games | 32,400 training games (10,800 + 21,600); 2.02 M decisions, about 8 M engine turns |
| Compute | one Apple M5 laptop, 9 worker processes; wall time 9.2 min + 23.8 min |
| Dependencies | numpy 2.3.5, Python 3.14 |

**League.** Half the games are against a scripted bot. Stage 1 weights them rush 0.3, scout 0.25, turtle 0.2, greedy 0.15 and random 0.1. Stage 2 weights them towards the ones stage 1 lost to: turtle 0.45, scout 0.25, rush 0.2, greedy 0.05, random 0.05. Of the other games, 30% are against a past checkpoint (one is added every 10 updates) and 20% against the current policy.

**How it got here.** The first runs learned to rush and stalled at about 53% against turtle. A fixed policy using the same actions ("economy, then a massed attack") beat turtle 95% of the time but lost to rush, so the actions were enough. What the network couldn't do was tell a turtle from a rush. Adding the three "where have enemy soldiers been" features fixed that. A run with a higher entropy bonus (0.03) learned turtle but forgot rush, and was dropped.

**Reproducibility.** Every random choice comes from the config's seed: game seeds, opponents, minibatches, and each bot's own sampling, which is seeded from its game as in the harness. Two runs of the same config on the same machine give bit-identical weights (`rl/tests/test_train.py`). Remaining nondeterminism: floating-point results can differ across CPUs and numpy/BLAS builds, so another machine may train slightly different weights.

## Results against the scripted baselines

Measured on the exported `boss.py`, run through the CLI runner in its own harness process. It played 200 seed pairs (seeds 1000–1199, each from both seats), 400 games per baseline. Those seeds were never used in training, and design choices were made while watching seeds 0–19. Scores count a draw as half a win, with a 95% Wilson interval. These are win rates in single games against fixed opponents, not a self-play rating.

| Baseline | W–D–L | Score | 95% CI |
|---|---|---|---|
| random | 400–0–0 | 100% | 99.0–100% |
| greedy | 400–0–0 | 100% | 99.0–100% |
| rush | 369–0–31 | 92.3% | 89.2–94.5% |
| scout | 336–0–64 | 84.0% | 80.1–87.3% |
| turtle | 309–0–91 | 77.3% | 72.9–81.1% |

Every lower bound is above 50%.

**In the ranked jail** (`scripts/boss_timing.py`): 40 ranked games against all five baselines from both seats, with every limit enforced. Per-turn CPU time as the host measures it, over 6,999 turns: p50 0 ms, **p99 1 ms**, max 3 ms, against a 100 ms turn budget. There were no timeouts, crashes or memory failures.

## Known weaknesses

Found by watching its losses on held-out seeds:

- **It is a soldier bot.** It spends most of its crystals on soldiers and few on workers, and in most games its soldiers hunt. When its attack stalls, it loses on score at turn 400. Almost all of its losses to turtle and scout go this way: the opponent ends with roughly twice its score.
- **Against rush it can leave home open.** Its two losses by Core destruction came after it switched to *attack* while rush's soldier stream was still arriving.
- **No real scouting.** It seldom builds a scout, so it learns about the opponent only when armies meet.
- **It has only seen five opponents** and itself. A player bot that out-mines it while holding a ring at home is the obvious counter, and it will probably lose to one.

## Benchmark, tracked over time

To be filled in once the boss is on the live ladder:

- boss against each scripted baseline (above);
- P(boss stronger than the best human bot);
- days until the first human bot is rated above the boss;
- the number of human bots above each anchor.
