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
