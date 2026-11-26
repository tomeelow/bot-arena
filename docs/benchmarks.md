# Benchmarks

Measurements that later decisions depend on. Each entry records the machine, the date and the exact command, so it can be re-run and compared.

## Engine speed (Phase 1)

**2026-11-25 · engine 0.1.0 · CPython 3.14.5 · Apple M5 (arm64, macOS)**

```bash
PYTHONPATH=engine/tests uv run python engine/tests/bench_engine.py
```

Times `step()` and `observe()` only, with no bot time, over the three golden games (4,895 turns, 17.3 units on the board on average):

| Operation | Cost |
|---|---|
| `new_game` (map generation) | 1.27 ms |
| `step` | 0.066 ms per turn (≈15,200 turns/s) |
| `observe` | 0.238 ms per call |
| `step` + both `observe`s | ≈1,840 turns/s |

**Reading it:** the rules are cheap, and fog computation dominates. A full 400-turn match costs the engine well under a second, so in ranked play bot time will dwarf engine time. For RL training (Phase 11), `visible_cells` is the first thing to optimise. Anything that replaces it must pass the fog tests unchanged.

The production VM (Ampere A1, ADR-005) will be slower than this laptop. Re-measure there in Phase 3.

## Map generation (Phase 1)

**2026-11-25 · engine 0.1.0**

All 10,000 seeds `0..9999` pass every check in `engine/tests/test_mapgen.py::check_map`: symmetry, connectivity, reachable deposits, home deposits and amount ranges. That took 24.9 s. CI checks the first 1,000 seeds on every run.

## Sandbox spike (Phase 3, ADR-002)

**2026-11-26 · Linux arm64 (Docker Desktop on Apple M5, kernel 7.0) · CPython 3.14.10, Pyodide 314.0.8, bubblewrap 0.12.0**

Each candidate was driven through the real `ProcessChannel` and harness. "Python speed" is a bot doing 14 full-map BFS runs per turn.

| Candidate | Cold start | Overhead per turn | Peak memory per bot | Python speed |
|---|---|---|---|---|
| CPython in bubblewrap (chosen) | 23 ms | 0.04 ms | 20 MiB | 13.5 ms/turn |
| Pyodide in Deno, in bubblewrap | 942 ms | 0.09 ms | 218 MiB | 35.0 ms/turn |
| CPython, no jail | 28 ms | 0.04 ms | 20 MiB | 13.6 ms/turn |

## Sandbox soak test (Phase 3)

**2026-11-26 · same machine · engine 1.0.0**

```bash
docker run --rm --privileged arena-sandbox python sandbox/soak.py --matches 1000 --parallel 8
```

1,000 ranked matches, 30% with an adversarial bot from `sandbox/adversarial/`, eight at a time, took 172 s.

| Check | Result |
|---|---|
| Platform errors (an exception out of `ranked_match`) | **0** |
| Jail processes or cgroups left behind | **none** |
| Host process peak memory, every 100 matches | 41.1 → 43.5 MiB, levelling off |
| Outcomes | 460 turn limit, 325 Core destroyed, 99 timeout, 52 memory, 51 invalid output, 13 crash |

**CPU per normal match** (scout vs turtle, both jailed, one at a time, median of 20): 0.18 s for the two bots, including interpreter start-up, plus 0.21 s on the host for the engine and protocol. That's **≈ 0.4 s** in total. The Ampere A1 will be slower; re-measure there in Phase 9 before setting the daily match cap.
