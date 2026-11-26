# Implementation Plan: Bot Arena — a sandboxed, rated programming game

> **Goal:** a public platform where people write Python bots, upload them, and watch them play a ranked ladder. The platform runs strangers' code safely, rates it with honest uncertainty, and costs nothing to run. It's a product with outside users, not a demo.
>
> **Headline target:** outside players with bots on a live ladder, where every rating carries a confidence range that has been checked against reality, every match can be replayed bit for bit, and no bot has ever taken the platform down.

---

## Progress tracker

Read this first. Update the status in the same branch that changes it (see `CLAUDE.md`, "Working with the plan").

Legend: ⬜ not started · 🟨 in progress · ✅ done

| # | Phase | Status | Depends on | Key deliverable |
|---|---|---|---|---|
| 0 | [Setup & decisions](#phase-0--setup--decisions) | ✅ | — | Repo skeleton, `make verify`, CI, ADRs |
| 1 | [Game rules & engine](#phase-1--game-rules--deterministic-engine) | ✅ | 0 | `GAME_RULES.md` v1, pure deterministic engine, property tests |
| 2 | [Bot API, starter kit, built-in bots](#phase-2--bot-api-starter-kit--built-in-bots) | 🟨 | 1 | Local runner, replay format v1, baseline bots, balance report |
| 3 | [Sandbox](#phase-3--sandbox) | ✅ | 2 | Jailed runner, adversarial suite passing |
| 4 | [Match infrastructure](#phase-4--match-infrastructure) | ✅ | 3 | Upload pipeline, queue, workers, replay store |
| 5 | [Ratings & matchmaking](#phase-5--ratings--matchmaking) | 🟨 | 4 | Rating service, matchmaker, synthetic-ladder validation |
| 6 | [API, auth & live spectating](#phase-6--api-auth--live-spectating) | ⬜ | 5 | FastAPI, GitHub login, websocket streaming |
| 7 | [Web frontend & viewer](#phase-7--web-frontend--viewer) | ⬜ | 6 | Ladder, bot pages, viewer with scrubber and logs |
| 8 | [Browser practice](#phase-8--browser-practice) | ⬜ | 2, 7 | Pyodide practice mode, cross-runtime determinism |
| 9 | [Zero-cost deployment](#phase-9--zero-cost-deployment) | ⬜ | 7 | Live site on free tiers, backups, budget guards, private alpha |
| 10 | [Observability & usage metrics](#phase-10--observability--usage-metrics) | ⬜ | 9 | Public stats page, platform health, alerts |
| 11 | [The RL boss](#phase-11--the-rl-boss) | ⬜ | 2 (train), 9 (ship) | Self-play boss on the ladder with a model card |
| 12 | [Launch & polish](#phase-12--launch--polish) | ⬜ | 10, 11 | README, docs, season 1, blog post, demo |

**Parallel track:** Phase 11 training only needs the engine and the built-in bots (Phases 1–2), so it can run offline any time from Phase 3 on. It sits late in the table because it ships onto a working ladder.

---

## Architecture overview

```
                 Static site (free static hosting)
 ┌──────────────────────────────────────────────────────────────────────┐
 │  Rules & starter kit · Ladder · Bot pages · Stats                     │
 │  Practice: Pyodide Web Workers ── engine + your bot + built-in bots   │
 │            (unrated, runs on the player's machine, zero server cost)  │
 │  Viewer ◄── one component for live matches and replays                │
 └──────────┬───────────────────────────────────────────────▲───────────┘
            │ HTTPS: login, upload, ladder, replays         │ WSS: live frames
            ▼                                               │
 ┌──────────────────────── One free-tier VM ─────────────────┴──────────┐
 │  Caddy (TLS) ─► FastAPI: GitHub login · uploads · ladder · websockets │
 │                    │                                                   │
 │                    ▼                                                   │
 │  SQLite (WAL): users · bots · versions · matches · results · ratings  │
 │       ▲  the queue is a table                                          │
 │       │                                                                │
 │  Scheduler: matchmaker · lease reaper ──► queued matches               │
 │                                              │                         │
 │  Workers (cores − 1), each runs one match:   ▼                         │
 │     engine (host side, trusted) ◄─JSON─► jail: bot A  (no net, limits) │
 │                                 ◄─JSON─► jail: bot B                   │
 │     → replay (orders) → re-simulate & verify → result → rating update  │
 │                                                                        │
 │  Replays on disk ──► backups to free object storage (Litestream/rclone)│
 └────────────────────────────────────────────────────────────────────────┘

 Offline (dev machine / free notebook GPU):
   RL self-play on the same engine ─► boss weights (.npz) ─► uploaded as a normal bot
```

**Core design principle:** there is one deterministic engine, and everything else is a different way of feeding it orders. The local CLI, browser practice, ranked workers and RL training all call the same `step()` and `observe()`. Bots sit behind a hostile-input boundary and only ever see their fogged, seat-relative observation. Because a match is fully defined by its seed and its order stream, every result can be re-simulated, every replay is a few kilobytes, and ratings can be rebuilt from scratch at any time.

---

## Scope for v1

**In:** 1v1 only · Python bots (a single `.py` file, or a `.zip` with `main.py` and data files) · one map size · ranked ladder with confidence ranges · version-vs-version comparison · live and replay viewer · browser practice against built-in bots and the boss · GitHub login · public usage stats.

**Out (on purpose):** free-for-all or team modes · languages other than Python · tournaments and brackets · chat or social features · paid anything · a polished mobile layout. These go under "What I'd do with more time".

**Originality:** the game is our own design. Genre conventions (grids, fog, resources) are fine. Don't copy the rules, names or art of existing bot-programming games.

---

## Phase 0 — Setup & decisions

**Goal:** scaffolding, a verify pipeline, and the decisions that are expensive to reverse, all in place before any game code exists.

### Repository structure
```
bot-arena/
├── engine/                 # pure-Python game engine, zero dependencies; runs on CPython and Pyodide
├── starter_kit/            # what players download: bot API, built-in bots, example bot, `arena` CLI
├── sandbox/                # in-jail harness, host-side runner, jail config, adversarial/ bots
├── server/                 # FastAPI app, queue, workers, scheduler, ratings, websocket fan-out
├── rl/                     # offline self-play training; never deployed
├── web/                    # static frontend: ladder, viewer, practice (Pyodide in Web Workers)
├── config/                 # limits.toml, ladder.toml — every tunable number lives here
├── docs/                   # ADR.md, GAME_RULES.md, implementation_plan.md, reports
├── deploy/                 # Caddyfile, systemd units, backup config, RUNBOOK.md
├── .github/workflows/      # verify on PR; deploy on main
├── pyproject.toml          # uv workspace root
├── Makefile                # `make verify` and friends
└── .env.example
```

### Tooling
```bash
uv init --bare --name bot-arena --python 3.14         # 3.14 = what Pyodide 314.x ships (ADR-001)
uv init --lib --name arena-engine engine              # zero runtime dependencies, keep it that way
uv init --lib --name arena-starter-kit starter_kit    # imported as `arena`
uv init --lib --name arena-sandbox sandbox
uv init --lib --name arena-server server
uv add --dev ruff "pyright[nodejs]" pytest import-linter
```
Each dependency is added in the phase that first uses it (hypothesis in Phase 1; FastAPI and openskill in Phases 5–6), not all up front.

Frontend: SvelteKit with the static adapter, in `web/` (ADR-006).

`make verify` runs `ruff check`, `ruff format --check`, `pyright`, `lint-imports`, `pytest`, plus `npm run check` and `npm test` in `web/`. Once the skeleton exists, run `/harden-repo` to tighten it.

### Guardrails as code, from day one
- **Engine purity:** ruff `banned-api` in `engine/pyproject.toml` bans clocks, I/O, network, concurrency and the module-level `random` functions. Ruff can't see builtins, so an AST test bans `hash()`, `id()`, `open()` and `input()`. `tests/test_guardrails.py` proves the bans fire, so loosening them breaks the build.
- **Import contracts (import-linter):** `arena_engine` imports nothing from the rest of the repo. More contracts are added once the packages they guard exist: `server` never imports `rl` (Phase 11), and `sandbox` host code never imports bot code (Phase 3).
- `.gitignore` covers `*.db`, `replays/`, `uploads/`, `*.npz`, `.env`.

### Architecture Decision Records (`docs/ADR.md`)
Same format as before: context, decision, reasoning, **alternatives considered and what would change our mind**.

1. **ADR-001 — Game shape and one engine.** 1v1, simultaneous moves, fog of war, integer-only deterministic engine in pure Python, shared by the CLI, the browser, the server and RL. No second implementation of the rules.
2. **ADR-002 — Sandbox runtime.** *Proposed* here and decided by the Phase 3 spike (Pyodide-in-Deno vs CPython in nsjail vs gVisor). Whatever the runtime, the OS-level jail is mandatory.
3. **ADR-003 — Rating system.** Recommendation: **OpenSkill (Weng–Lin)**. It updates after every match, which suits a continuous ladder; its μ/σ give the confidence statements directly; and it's MIT-licensed. Glicko-2 is built around batched rating periods. TrueSkill is patented and trademarked by Microsoft. Fine for a hobby project, but a reason to prefer the open alternative.
4. **ADR-004 — SQLite as database and queue** on one server, in WAL mode. Postgres, Redis and Celery are rejected until the single-server design measurably fails.
5. **ADR-005 — Hosting.** One free-tier VM, free static hosting, free object storage for backups. **Record each service's current terms and the date you checked them**, because free tiers change.
6. **ADR-006 — Frontend.** SvelteKit (static adapter), a Canvas 2D viewer, CodeMirror 6 for the practice editor. React is the alternative if its name on a CV outweighs Svelte's smaller footprint.
7. **ADR-007 — Replay format.** Orders are canonical; viewer frames are derived. The engine version is in every replay.

**Deliverable:** a skeleton repo where `make verify` passes locally and in CI, with the ADRs written.

**Exit criteria**
- [x] uv workspace and `web/` skeleton; `make verify` green locally and in GitHub Actions (PR #1, run 45704307785)
- [x] Engine purity guardrails enforced, and `tests/test_guardrails.py` proves that `import time` and the other bans fail lint in `engine/`
- [x] ADR-001 and ADR-003 to ADR-007 written; ADR-002 opened as *proposed*
- [x] Free-tier terms for every candidate service checked and dated in ADR-005 (uptime monitoring and notebook GPUs deferred to Phases 10 and 11)
- [x] `.env.example` and `.gitignore` in place

---

## Phase 1 — Game rules & deterministic engine

**Goal:** a game worth writing bots for, and an engine you can trust bit for bit. Everything else is built on top of it.

### Draft v1 ruleset (finalize and freeze in `docs/GAME_RULES.md`)
- **Map:** a 32×32 grid generated from the seed, 180° rotationally symmetric, with a guaranteed path between the cores. Each tile is open, wall, or a crystal deposit (finite). Terrain is known from turn 0 (the symmetry would give it away anyway). Units and deposit levels are hidden by fog.
- **Start:** each player has a **Core** (HP, banked crystals, spawns units) and two Workers.
- **Units (v1):**
  - **Worker**: mines an adjacent deposit, carries up to *N* crystals, unloads at its Core. Can't attack.
  - **Soldier**: attacks an adjacent enemy unit or Core. Costs more and has more HP.
  - **Scout**: cheap, fragile, large vision radius. Information has a price.
- **Orders:** one per unit per turn: `move(dir)`, `mine(dir)`, `unload`, `attack(dir)` or `hold`. The Core can `spawn(kind, dir)` at most once per turn. Invalid orders turn into `hold` and are reported privately to the bot that sent them.
- **Resolution:** all orders apply at once, in fixed phases. (1) Attacks resolve from start-of-turn positions and all damage lands at the same time. (2) Destroyed units are removed. (3) Moves: if two or more units target the same cell, or two units try to swap places, every unit involved stays put. (4) Mining and unloading: a deposit with less than the total demand splits it evenly, and the remainder stays in the deposit. (5) Spawns. (6) Visibility. (7) Win check. **No phase depends on seat order.**
- **Fog:** every unit and Core sees the cells within its vision radius. Enemy units show kind, position and HP, with no ids.
- **End:** a Core reaches 0 HP (both at once is a draw), or the game hits turn 400, in which case more banked crystals wins and a tie is a draw.
- **Where the depth comes from:** economy (workers), aggression (soldiers) and information (scouts) under fog. Rushing beats greed, defense beats rushing, greed beats defense, and scouting tells you which one you're facing. Phase 2's balance report checks whether that actually holds; we don't assume it.

### Engine API: the whole public surface
```python
# engine/src/arena_engine/__init__.py (orders, observations and events are seat-relative)
ENGINE_VERSION: str

def new_game(rules: Rules, seed: int) -> GameState: ...
def map_info(state: GameState, seat: int) -> MapInfo: ...             # public from turn 0
def observe(state: GameState, seat: int) -> Observation: ...          # fogged
def step(state: GameState, orders: Mapping[int, Sequence[Order]]) -> StepResult: ...  # state + private events
def outcome(state: GameState) -> Outcome | None: ...                  # None while running
def state_hash(state: GameState) -> str: ...                          # sha256 of a canonical encoding
def parse_order(data: object) -> Order: ...                           # strict; reads untrusted JSON
```

### Tests: the engine's contract
- **Rules:** one test per conflict case in `GAME_RULES.md` (collisions, swaps, simultaneous kills, split mining, a spawn cell that's blocked, both Cores dying at once).
- **Determinism:** the same seed and order stream give the same `state_hash` across separate processes with different `PYTHONHASHSEED`.
- **Seat symmetry:** with deterministic bots, swapping seats gives the mirrored game:
  ```python
  @given(seeds())
  def test_seat_swap_mirrors_the_game(seed):
      g1 = play(GreedyBot(), RushBot(), seed)
      g2 = play(RushBot(), GreedyBot(), seed)
      assert g2.outcome == g1.outcome.mirrored()
      assert all(state_hash(mirror(a)) == state_hash(b) for a, b in zip(g1.states, g2.states))
  ```
- **Fog (the observation rule):**
  ```python
  @given(states_differing_only_in_fog())
  def test_fog_hides_everything_hidden(case):
      a, b, seat = case   # a, b differ only in what `seat` cannot see (enemy units, crystals, deposits)
      assert observe(a, seat) == observe(b, seat)
  ```
- **Invariants** (hypothesis, random legal order streams): no unit in a wall; at most one unit per cell; crystals are conserved (deposits + carried + banked + spent = initial); HP never goes negative; maps are symmetric and connected for 10k seeds.
- **Golden order streams:** a handful of recorded games with their expected final hashes, checked in CI on **CPython and on Pyodide (Node)**. If the two runtimes diverge, we find out now, not in Phase 8.
- **Benchmark:** turns per second on a mid-game state, recorded in `docs/benchmarks.md`. It isn't a gate yet; Phase 11 decides whether it needs to be faster.

**Deliverable:** `docs/GAME_RULES.md` v1 and an `engine/` package that satisfies all of the above.

**Exit criteria**
- [x] `GAME_RULES.md` v1 written, with a worked example for every conflict case
- [x] Engine implements v1 behind the public API above, with zero dependencies
- [x] Rules tests for every conflict case (`engine/tests/test_rules.py`)
- [x] Determinism, seat-symmetry, fog and invariant property tests pass (maps also checked over 10,000 seeds)
- [x] Golden hashes are identical on CPython and Pyodide in CI (PR #2, run 45708699814)
- [x] Engine benchmark recorded (`docs/benchmarks.md`)

---

## Phase 2 — Bot API, starter kit & built-in bots

**Goal:** a stranger can write a bot in 15 minutes, run a match locally, and understand what happened. The built-in bots set up a strength ladder and test the game's balance.

### Bot API
```python
# my_bot.py — a complete bot
from arena import Bot, Observation, Order

class MyBot(Bot):
    def act(self, obs: Observation) -> list[Order]:
        orders = []
        for worker in obs.my_units("worker"):
            if worker.cargo_full:
                orders.append(worker.move_toward(obs.my_core.pos))
            else:
                orders.append(worker.mine_or_approach(obs.nearest_deposit(worker.pos)))
        if obs.my_core.crystals >= obs.cost("worker"):
            orders.append(obs.my_core.spawn("worker"))
        self.log(f"turn {obs.turn}: {len(orders)} orders")   # visible to you in your replays
        return orders
```
The starter kit provides helpers (BFS pathing, distances, nearest-X). The bot also gets `self.rng`, seeded from the match seed. Bots that use the wall clock can't be reproduced, which is exactly why replays store orders.

### Protocol (host ↔ in-jail harness), JSON lines
```
host → bot   {"t": "init",   "rules": {…}, "limits": {…}, "rng_seed": …}
bot  → host  {"t": "ready"}
host → bot   {"t": "turn",   "n": 17, "obs": {…}}
bot  → host  {"t": "orders", "n": 17, "orders": […], "log": "…"}
```
The harness sends `print` output into `log`. The host truncates logs and rejects any reply that is malformed, oversized or for the wrong turn. The local runner uses **the same harness and protocol** in a plain subprocess, with no jail; limits there are advisory warnings.

### Local CLI
```bash
arena match my_bot.py builtin:greedy --seed 7 --out replay.json.gz
arena show replay.json.gz --turn 120                  # ASCII board for quick debugging
arena tournament builtin:* my_bot.py --seed-pairs 50  # round robin, both seats per seed
```

### Replay format v1 (ADR-007)
```jsonc
{
  "format": 1,
  "engine_version": "1.0.0",
  "seed": 7,
  "config": { … },
  "players": [{ "seat": 0, "bot": "builtin:greedy", "code_sha256": "…" }, …],
  "turns": [{ "orders": [[…], […]], "cpu_ms": [12, 31] }, …],
  "outcome": { "winner": 0, "reason": "core_destroyed", "turns": 214 },
  "final_hash": "sha256:…"
}
```
Bot logs live in a separate file, owner-only and size-capped. Loading a replay re-simulates it and checks `final_hash`.

### Built-in bots: reference points and teaching examples
| Bot | Strategy | Role |
|---|---|---|
| `random` | Random legal orders | The floor |
| `greedy` | Workers only, mine nearest | Pure economy |
| `rush` | Early soldiers straight at the Core | Pure aggression |
| `turtle` | Economy plus soldiers guarding the Core | Defense |
| `scout` | Scouts first, then counters what it sees | Adaptation |

Plus a `noisy(bot, ε)` wrapper that replaces each order with a random legal one with probability ε. It produces a family of bots with a known strength order, which Phase 5 uses for validation.

### Balance report (`docs/balance.md`, generated by a script)
- A round-robin win matrix among the built-ins, *N* seed pairs each, with 95% confidence intervals.
- **Seat advantage:** seat-0 win rate over mirrored pairs. The target is statistically indistinguishable from 50%.
- Draw rate, game-length distribution, and the share of games that reach the turn limit.
- **Dominance check:** no built-in beats every other one with a CI lower bound above 50%. If one does, change the rules now. Rule changes are cheap before launch and expensive after.

**Deliverable:** `starter_kit/` with the `arena` CLI, five built-in bots, replay format v1, and a balance report. The rules are then frozen as engine `1.0.0`.

**Exit criteria**
- [x] Bot API, harness and JSON protocol, with strict host-side parsing (schema, size, turn number)
- [x] `arena match / show / tournament` CLI
- [x] Replay format v1; loading re-simulates and verifies the hash
- [x] Five built-in bots and the `noisy()` wrapper (`builtin:NAME~EPS`); they send no invalid orders
- [x] Balance report: the seat-advantage CI covers 50%, and no built-in dominates (`docs/balance.md`; turtle vs rush is even, so the intended cycle is incomplete)
- [x] Rules frozen as engine `1.0.0` (2026-11-25)
- [ ] Someone other than the author wrote a working bot from the starter-kit README alone (record how long it took)

---

## Phase 3 — Sandbox

**Goal:** run any stranger's Python safely on a single shared server. This is the main engineering problem of the project.

### Threat model
| Attacker goal | Examples | Defense |
|---|---|---|
| Take the platform down | Infinite loop, memory bomb, fork bomb, filling the disk, flooding output | cgroup CPU, memory and pids limits; size-capped tmpfs; host-side read limits; wall-clock kill |
| Escape or reach the host | Reading files, network access, `ctypes`, `import js` | No network namespace, minimal read-only fs, empty env, seccomp, non-root, runtime with no permissions |
| Cheat within a match | Reading the opponent's code or memory, faking timings, tampering with the harness | One jail per bot, host-measured time, host-side validation |
| Cheat on the ladder | Sybil bots feeding wins to a main bot | Phase 5: same-owner exclusion, per-user caps |
| Attack spectators | HTML or JS in bot names or logs | Phase 7: render as text, strict CSP |

### Spike → ADR-002
Build the smallest possible runner for each candidate and measure it **on the target VM**: ARM64 with 2 OCPUs and 12 GB (ADR-005). Per-bot overhead comes straight out of match throughput on a machine that small.

| Candidate | Isolation layers | Same runtime as browser practice? |
|---|---|---|
| A. Pyodide in Deno (no permissions) inside an OS jail | WASM + runtime permissions + OS | **Yes**: if it works in practice, it works in ranked |
| B. CPython in nsjail or bubblewrap, with seccomp and cgroups | OS | No |
| C. CPython in Docker with gVisor (`runsc`), `--network none`, read-only | User-space kernel | No |

Measure for each: cold start per bot, per-turn round-trip overhead, memory per bot, whether numpy is available, how it does against the adversarial suite, and how much operational work it takes. The default leaning is **A**, because of parity with practice, but the measurements decide. With any candidate, the OS layer (namespaces, cgroups, read-only fs, empty env, non-root) is mandatory.

**Decided 2026-11-26: B.** Pyodide cost 40× the start-up, 11× the memory and 2.6× the CPU per turn. The measurements and reasoning are in ADR-002.

### Limits (`config/limits.toml`, starting proposals)
```toml
[bot]
upload_max_bytes        = 2_000_000   # .py, or .zip with main.py; the boss gets the same cap
memory_mb               = 256
init_cpu_ms             = 2_000
turn_cpu_ms             = 100         # per-turn budget
time_bank_cpu_ms        = 10_000      # overruns draw from the bank; an empty bank is a timeout loss
turn_wall_ms_backstop   = 2_000       # a sleeping bot burns no CPU, so the wall clock kills it
reply_max_bytes         = 65_536
log_max_bytes_per_turn  = 2_048
log_max_bytes_per_match = 262_144
```

### Time accounting: the host measures, the bot never reports
```python
before = cpu_usage_us(jail)                       # cgroup v2 cpu.stat usage_usec
reply = channel.request(turn_msg, timeout=limits.turn_wall_ms_backstop / 1000)
used_ms = (cpu_usage_us(jail) - before) / 1000
bank_ms -= max(0, used_ms - limits.turn_cpu_ms)
if reply is None or bank_ms < 0:
    return forfeit(seat, EndReason.TIMEOUT)
```

### How a match can end
```python
class EndReason(StrEnum):
    CORE_DESTROYED = "core_destroyed"
    TURN_LIMIT     = "turn_limit"
    TIMEOUT        = "timeout"          # bot's fault → loss
    CRASH          = "crash"            # bot's fault → loss
    MEMORY         = "memory"           # bot's fault → loss
    INVALID_OUTPUT = "invalid_output"   # bot's fault → loss
    PLATFORM_ERROR = "platform_error"   # our fault → match void, never rated
```

### Adversarial suite (`sandbox/adversarial/`)
Every bot here must end in its expected `EndReason`, with the opponent unaffected and the host unchanged (no stray processes, cgroups or files, memory back to baseline).

| Bot | What it tries | Expected |
|---|---|---|
| `infinite_loop` | `while True: pass` during a turn | `timeout` |
| `slow_init` | Spins during setup | `timeout` |
| `sleeper` | `time.sleep(3600)` (uses no CPU) | `timeout` via the wall-clock backstop |
| `memory_bomb` | Allocates until it dies | `memory` |
| `fork_bomb` | `os.fork()` / `subprocess` in a loop | Blocked by the pids limit, then `crash` or `timeout` |
| `thread_bomb` | Thousands of threads | Blocked; the match continues or the bot loses |
| `network` | Socket connect, DNS, `urllib`, `fetch` via `import js` | Fails inside the jail; no packet leaves |
| `fs_read` | `/etc/passwd`, `/proc/self/environ`, other bots' files | Nothing sensitive exists in the jail; env is empty |
| `fs_fill` | Writes until the disk is full | tmpfs cap hit; host disk untouched |
| `stdout_flood` | Prints gigabytes | Output truncated by the host; `invalid_output` if the protocol breaks |
| `huge_reply` | A reply bigger than `reply_max_bytes` | `invalid_output` |
| `malformed` | Not JSON, wrong schema, wrong turn number, replayed old turn | `invalid_output` |
| `early_exit` | `sys.exit()`, `os._exit()` mid-match | `crash` |
| `signal_ignorer` | Traps SIGTERM | Killed with SIGKILL at the deadline |
| `recursion_bomb` | Deep recursion, C-stack overflow | `crash` |
| `harness_tamper` | Monkeypatches the harness, fakes timing fields | No effect: the host ignores self-reported data |
| `ctypes_escape` | `ctypes` and other native tricks | Fails inside the jail |
| `parser_bomb` | Pathologically nested source | Fails during in-jail validation; the host never parses it |

**Deliverable:** a jailed bot runner behind the same harness protocol, plus the adversarial suite in CI.

**Exit criteria**
- [x] Spike measurements recorded; ADR-002 accepted (CPython in bubblewrap with seccomp and cgroups)
- [x] Every bot gets a fresh jail per match, destroyed at the end and never reused
- [x] Host-measured CPU time with a time bank and a wall-clock backstop
- [x] Adversarial suite (every row above) passing in CI on Linux (PR #4, run 45780771449, x86_64; also arm64 locally)
- [x] Soak test: 1,000 matches mixing normal and adversarial bots, with zero platform errors, no leaked processes, cgroups or temp files, and flat memory (`docs/benchmarks.md`)
- [x] CPU-seconds per match measured and recorded (it feeds the Phase 9 capacity budget): ≈ 0.4 s on the dev machine

---

## Phase 4 — Match infrastructure

**Goal:** upload → validate → queue → play → store, surviving a crash at every step.

### Data model (SQLite, WAL mode; migrations are plain SQL files applied in order)
```sql
users         (id, github_id UNIQUE, handle, created_at)
bots          (id, owner_id, name, created_at)                       -- a lineage of versions
bot_versions  (id, bot_id, n, code_sha256, parent_id, status, created_at)
              -- status: pending → validating → active | rejected;  active → retired
matches       (id, kind, status, seed, engine_version, priority, worker_id, lease_until,
               created_at, finished_at)
              -- kind: placement | ranked | comparison;  status: queued → running → done | void
match_players (match_id, seat, bot_version_id)
results       (match_id PRIMARY KEY, winner_seat, end_reason, turns, replay_sha256)
ratings       (bot_version_id PRIMARY KEY, mu, sigma, games)          -- derived, rebuildable
```

### The queue is a table
```sql
-- inside BEGIN IMMEDIATE
UPDATE matches
SET status = 'running', worker_id = :worker, lease_until = :now + :lease
WHERE id = (SELECT id FROM matches WHERE status = 'queued' ORDER BY priority DESC, id LIMIT 1)
RETURNING id, seed, engine_version;
```
There are `cores − 1` worker processes, each playing one match at a time, with one core left for the API. A reaper marks matches with an expired lease as `void` (never rated) and queues the pairing again.

### Upload pipeline
1. Store the bytes under their sha256 (identical uploads are deduplicated). **The host does nothing else with them.**
2. Inside the jail: unpack, import, run setup, and play a smoke match against `builtin:random`. Validation errors go back to the owner, truncated and rendered as text.
3. If it passes, the version becomes `active`, the bot's previous version is retired, and placement matches are queued (Phase 5).

### Match lifecycle (in a worker)
Claim → start two jails → engine loop → write the replay (temp file, then rename) → **re-simulate from orders and compare the final hash** → in one transaction, write the result and mark the match `done` → update ratings. Any exception in *our* code voids the match and logs `platform_error` with the match id.

Replays are stored content-addressed: `replays/<sha[:2]>/<sha>.json.gz`.

**Deliverable:** the end-to-end match pipeline running locally with N workers.

**Exit criteria**
- [x] Schema and migrations (`server/src/arena_server/migrations/`)
- [x] Upload pipeline with in-jail validation and errors visible to the owner (`sandbox/tests/test_uploads_in_jail.py`)
- [x] Race-free queue claims: 8 workers and 500 matches, each played exactly once (test)
- [x] `kill -9` on a worker mid-match → match voided, no rating change, pairing re-queued (test)
- [x] Every stored replay re-simulates to its recorded hash (the worker checks before recording a result)
- [x] A platform error can never produce a rated result (tests: platform errors, unreproducible replays and lost leases all void)

---

## Phase 5 — Ratings & matchmaking

**Goal:** ratings that converge quickly, admit what they don't know, and hold up to scrutiny.

### Ratings are a fold over results
```python
def rebuild_ratings(results: Iterable[Result]) -> dict[VersionId, Rating]:
    ratings: dict[VersionId, Rating] = defaultdict(prior)
    for r in results:                                   # ordered by (finished_at, id)
        ratings[r.a], ratings[r.b] = update(ratings[r.a], ratings[r.b], r.score)
    return ratings
```
Incremental live updates and a full rebuild must agree exactly (test). This lets us change the rating system later, rebuild, and compare.

**New versions:** start from the parent version's μ with σ reset to the prior σ. That converges faster than starting from scratch and stays honest because σ is wide. *(Decision to confirm in ADR-003.)*

### Saying how sure we are
```python
def p_stronger(a: Rating, b: Rating) -> float:
    """P(skill_a > skill_b): a statement about skill, not about the next game."""
    return normal_cdf((a.mu - b.mu) / sqrt(a.sigma**2 + b.sigma**2))

def p_win(a: Rating, b: Rating, beta: float) -> float:
    """P(a beats b in one game): adds per-game performance noise."""
    return normal_cdf((a.mu - b.mu) / sqrt(a.sigma**2 + b.sigma**2 + 2 * beta**2))
```
The site's "A is stronger than B with 87% confidence" is `p_stronger`. Match previews use `p_win`. The UI labels them differently.

### Leaderboard
Ranked by the conservative score `μ − k·σ` (k is in config; 3 is the TrueSkill convention). The interval is shown. A bot is **provisional** until σ drops below the threshold.

### Matchmaker
```python
def next_pairing(active: list[BotRating], recent: RecentGames, rng: Random) -> tuple[BotRating, BotRating]:
    bot = max(active, key=lambda b: b.sigma + staleness_bonus(b))            # most to learn
    pool = [c for c in active if c.owner != bot.owner and not recent.saturated(bot, c)]
    weights = [max(1 - abs(2 * p_win(bot, c, BETA) - 1), EXPLORE_FLOOR) for c in pool]  # close games teach most
    return bot, rng.choices(pool, weights)[0]
```
Each pairing is played as a **mirrored pair** (same seed, both seats), which cancels seat and map luck.

- **Placement:** a new version first plays the built-in **anchors** (`random`, `greedy`, `rush`, `turtle`, `scout`). The anchors stay on the ladder for good; their fixed strength pins the scale and makes rating drift visible.
- **Integrity:** no rated games between bots of the same owner; a cap on active bots per user.

### Version comparison ("is v4 better than v3?")
The owner starts it, and it's rate-limited. It plays K seeds × 2 seats as unrated `comparison` matches and reports W/D/L, the score with a 95% Wilson interval, P(v4 stronger), and a link to every lost game. SPRT early stopping is optional.

### Validate on synthetic ladders before users rely on it
- **Population:** `noisy(bot, ε)` for every built-in and ε ∈ {0, 0.1, …, 0.9}. **Ground truth:** a long round-robin fitted with Bradley–Terry.
- **Ordering:** Kendall τ between the ladder ranking and the ground truth, as a function of games played.
- **Calibration:** bin the `p_win` predictions and compare them with observed win rates (reliability plot, Brier score, log loss). Because ground truth is known here, `p_stronger` can be checked too: among pairs we called "87% stronger", about 87% should actually be stronger.
- **Convergence:** the number of games until a newcomer's σ falls below the threshold.
- Targets (e.g. τ ≥ 0.9 within 50 games per bot) are written down **before** the first run. If one is missed, report it and fix the system.

**Deliverable:** the rating service, matchmaker, placement and version comparison, plus `docs/ratings_validation.md`, which is the evidence that "87%" means 87%.

**Exit criteria**
- [x] Live updates and a full rebuild agree exactly (test)
- [x] Leaderboard by conservative score, with intervals and a provisional state
- [x] Matchmaker invariants as property tests: never the same owner, always mirrored pairs, exploration floor respected
- [x] Placement against anchors
- [x] Version comparison with a CI and links to losses
- [x] Synthetic-ladder validation report: ordering, calibration and convergence measured against targets set beforehand (`docs/ratings_validation.md`, ADR-008)
- [ ] The validation's ordering (τ ≥ 0.90 at 50 games) and convergence (provisional left within 50 games) targets met on fresh seeds. Calibration and "X% stronger" already pass; see ADR-008 for the misses and what to try next

---

## Phase 6 — API, auth & live spectating

**Goal:** a small, boring HTTP and websocket API in front of the match system.

### Endpoints
```
GET  /api/ladder                          leaderboard: conservative score, interval, provisional
GET  /api/bots/{id}                       versions, rating history, recent matches
POST /api/bots/{id}/versions              upload (auth, rate-limited)
POST /api/compare                         version head-to-head (auth, rate-limited)
GET  /api/matches/{id}                    metadata + outcome
GET  /api/matches/{id}/frames             viewer frames, derived from the replay, cached
GET  /api/matches/{id}/logs/{seat}        owner only
WS   /ws/matches/{id}                     live frames; a late joiner gets the history first
GET  /api/stats                           public usage metrics (Phase 10)
GET  /auth/github/login · /auth/github/callback
GET  /health
```

- **Frames:** a per-turn delta of the full state, plus per-seat visibility masks. Live and replay use the same encoding.
- **Live fan-out without a broker:** the worker appends each turn's frame to `live/<match_id>.jsonl`. The websocket handler sends the history, then tails the file. When the match ends, the replay takes over. A live match really is a replay that's still being written.
- **Auth:** GitHub OAuth; session cookie that is `HttpOnly`, `Secure` and `SameSite=Lax`, signed with a key from the environment. Only the GitHub id and handle are stored.
- **Caps:** uploads and comparisons per user per day; concurrent websocket viewers per match and overall (all in config).

**Exit criteria**
- [ ] Endpoints with Pydantic schemas; OpenAPI published
- [ ] GitHub login works; only id and handle are stored
- [ ] Upload and compare rate limits enforced (tests)
- [ ] Two clients watch the same live match, and a late joiner catches up from turn 0
- [ ] The logs endpoint refuses non-owners (test)

---

## Phase 7 — Web frontend & viewer

**Goal:** make the whole system understandable within five seconds of opening it, and make it easy to see exactly where your bot lost.

### Pages
Home (what this is, top of the ladder, matches live right now) · Rules & starter kit · Ladder · Bot page (rating history with a σ band, versions, recent matches, compare versions) · Match viewer · My bots (upload, validation status, logs) · Practice (Phase 8) · Stats (Phase 10).

### Viewer
- A Canvas 2D board rendered from frames. Timeline scrubber, play/pause, speed control, ±1 turn steps, keyboard shortcuts.
- **Vision toggle:** omniscient, seat 0's view, or seat 1's view, so you can see exactly what each bot saw.
- **Advantage graph:** the difference in banked crystals plus unit value over time. Click to jump to a turn. The biggest swing is highlighted; that's where your bot lost.
- Event markers: units lost, Core damaged, invalid orders (owner only).
- A per-turn log panel, owner only, synced to the scrubber.
- Live mode is the same component reading a frame list that keeps growing.

### Security
Names, descriptions and logs render as text. Strict CSP with no inline scripts.

**Exit criteria**
- [ ] All pages above, as a static build
- [ ] Viewer: scrubber, vision toggle, advantage graph, event markers, owner logs
- [ ] Live and replay share one viewer component
- [ ] XSS test: a bot named `<img src=x onerror=alert(1)>`, with logs to match, renders as plain text

---

## Phase 8 — Browser practice

**Goal:** write and test a bot without installing anything, at zero server cost.

- Each bot runs in **its own Pyodide Web Worker** (the engine runs alongside the built-in opponent) and talks to the page using the same JSON protocol as the server. The user's code comes from a CodeMirror 6 editor or a dropped file.
- If the user's bot hangs past the backstop, its worker is terminated and the bot is reported as timed out. The page doesn't freeze.
- **Timing in the browser is advisory.** Practice is labeled *unrated, timing indicative*, because the player's machine isn't the server.
- Practice replays open in the same viewer, can be downloaded, and replay identically with the local CLI.
- Only the user's own code and our built-in bots (later the boss too) ever run in the browser.
- A "Submit to ladder" button hands the current code to the upload flow.

**Exit criteria**
- [ ] Practice page: editor, opponent picker, run, watch
- [ ] A hung user bot is terminated and reported without freezing the page
- [ ] The browser and the CLI produce identical replays for the same seed and bots (Playwright e2e test)
- [ ] Someone else, in a fresh browser profile, went from landing page to a bot that beats `random` to a submitted bot, with no local install

---

## Phase 9 — Zero-cost deployment

**Goal:** public, costing nothing to run, and easy to restore.

### Topology
- **Frontend:** free static hosting (Cloudflare Pages or GitHub Pages).
- **Backend:** one free-tier VM running Caddy (automatic TLS) in front of systemd units: `arena-api` (uvicorn), `arena-worker@1..N`, `arena-scheduler` (matchmaker, lease reaper, rating catch-up).
- **Backups:** Litestream streams SQLite continuously to free object storage; replays sync nightly with rclone.
- **Before deploying, re-verify every free tier:** limits, idle-instance reclamation policies, ARM capacity in the chosen region, egress, whether a card is required. Record the date in ADR-005. A domain name is the only optional cost; a free subdomain works.

### Capacity budget (filled in from Phase 3 measurements)
```
cpu_seconds_per_match  = measured in Phase 3
worker_cores           = cores − 1
max_matches_per_day    = worker_cores × 86_400 × target_utilisation / cpu_seconds_per_match
```
On today's Always Free shape (2 OCPUs, ADR-005), `worker_cores` is 1. That number becomes the daily match cap in `config/ladder.toml`. The matchmaker spends it on the most informative pairings first (highest σ).

### Budget guards
A daily match cap · ranked replays kept, the frame cache evicted LRU, logs expired after N days · a disk-usage alarm · upload, compare and viewer caps · a **kill switch** that pauses the ladder by stopping the scheduler without losing queued matches.

### CI/CD
On a PR: `make verify`. On merge to `main`: build `web/` and deploy it to static hosting, then deploy the server to the VM. Secrets live in GitHub Actions secrets. `deploy/RUNBOOK.md` covers deploy, rollback, restore, secret rotation, the kill switch, and how to bump the engine version (which starts a new season).

**Exit criteria**
- [ ] Site live on free tiers; billing dashboards checked and showing €0
- [ ] Restore drill: a fresh VM rebuilt from backups in under an hour, with the ratings rebuild matching
- [ ] Capacity budget computed from measurements, with caps in config
- [ ] Kill switch tested
- [ ] Private alpha: 3–5 outside people uploaded bots, and their issues were collected and triaged

---

## Phase 10 — Observability & usage metrics

**Goal:** know whether the platform works and whether anyone uses it, measured from the first day of the public launch.

### Platform health (admin page, structured JSON logs, no paid APM)
Match duration · distribution of end reasons · **`platform_error` rate (target: 0)** · queue depth and wait time · worker utilization · jail start latency · disk usage.

### Usage metrics (public `/stats` page; one SQL query per metric over our own DB)
| Metric | Definition |
|---|---|
| Submitted bots | Distinct bots with at least one validated version |
| Versions per day | Validated uploads per day |
| Active players (7d) | Users with an upload or a signed-in visit in the last 7 days |
| Matches per day | Rated matches completed per day |
| Rating convergence | Median rated games (and hours) until a new version's σ < threshold |
| Time to first match | From upload to first completed rated match, p50/p95 |
| Sandbox outcomes | Share of matches ending in timeout, crash, memory or invalid output |

**Exit criteria**
- [ ] Every metric defined as a tested query (against a fixture DB)
- [ ] Public stats page and admin health page
- [ ] Free alerts (uptime checker email or similar) for `platform_error > 0`, disk above 80%, and queue wait above its threshold
- [ ] No third-party trackers (checked in the browser network tab)

---

## Phase 11 — The RL boss

**Goal:** a self-play bot strong enough to be worth beating, documented honestly, playing under exactly the same rules as everyone else.

### Training (offline, in `rl/`; PyTorch is a dependency only here)
- **Environment:** the engine wrapped as a two-player PettingZoo `ParallelEnv`, using the **same `observe()`** bots get, so there's no gap between training and serving observations.
- **Encoding:** grid channels (terrain, own units by kind, visible enemies, deposits, visibility mask, cargo) plus scalars (turn, crystals). **Actions:** a per-cell action map masked to your own units' legal orders, which handles any number of units.
- **Algorithm:** PPO with a small convolutional net, trained against a **league**: the latest policy, a pool of past checkpoints, and the scripted bots. The league prevents strategy collapse and forgetting.
- **Progress is measured against fixed opponents:** every N updates, play the frozen scripted baselines on fixed seed pairs. Self-play Elo inflates and is never the headline.
- **Engine speed:** if throughput limits training, profile first. A batched engine for training is allowed only if differential tests on recorded replays show it matches the reference engine.
- **Compute:** a dev machine or free notebook GPUs (check the current terms). Never the production VM.

### Shipping
- Weights exported to `.npz` with a **pure-numpy** forward pass. Must fit inside the per-turn CPU budget with margin (p99 in the production sandbox) and inside the upload size cap.
- Uploaded through the **normal pipeline** under a dedicated `arena-boss` account. Same jail, same limits, same observations.
- Weights are attached to a GitHub release, not committed.

### Model card (`docs/boss_model_card.md`)
What it is · training setup (algorithm, network size, environment steps, compute, wall time) · league composition · win rate against each scripted baseline with a 95% CI over *N* seed pairs · ladder rating when published · known weaknesses, found by watching its losses · engine version · weight hash · date.

### Benchmark, tracked over time
Boss vs each scripted baseline · P(boss stronger than the best human bot) · **days until the first human bot is rated above the boss** · number of human bots above each anchor.

**Exit criteria**
- [ ] RL env wrapper uses the engine's `observe()`; tests show it matches the CLI runner's results
- [ ] Training reproducible from config and seed (remaining nondeterminism documented)
- [ ] Boss beats every scripted baseline with a 95% CI lower bound above 50%
- [ ] Inference p99 within the turn budget in the production sandbox; bundle within the upload cap
- [ ] Uploaded through the normal pipeline; model card published

---

## Phase 12 — Launch & polish

### README sections (non-negotiable)
1. What it is, in one paragraph, plus a GIF of a match.
2. Play in three steps (link to practice).
3. Architecture diagram (redraw the overview above).
4. **The sandbox:** the threat model and how each threat is handled, with a link to the adversarial suite.
5. **Honest ratings:** results from the synthetic-ladder validation (ordering, calibration, convergence).
6. **The boss:** model card summary and benchmark.
7. **Real usage:** live numbers from `/stats`.
8. **Zero-cost architecture:** what runs where, and why it costs nothing.
9. Local development setup.
10. "What I'd do with more time": three honest bullets (e.g. other languages via WASM, free-for-all and team modes, tournaments).

### Launch
- **Seasons:** season 1 starts at launch with the engine version frozen. An incompatible rule change starts a new season with a ladder reset.
- **Announce:** the author posts, picking the channels (e.g. Show HN, Python communities, university groups). Metrics are tracked from day one.
- **Feedback:** GitHub Issues/Discussions. Triage weekly in the first month.

### Blog post (400–600 words)
Problem → the one decision worth explaining (running strangers' Python for free, *or* making "87% confident" mean something) → one surprising finding (calibration, or how fast humans caught up with the boss) → link to the live site.

### Demo video (90 seconds)
Write a bot in browser practice → submit → watch its first ranked match live → the ladder with confidence ranges → the boss's model card.

**Exit criteria**
- [ ] README complete, with real numbers
- [ ] Season 1 started
- [ ] Blog post and demo video published
- [ ] First-month targets written down before launch (e.g. ≥ 20 bots from ≥ 10 people) and actual numbers reported, whether or not they hit the targets

---

## Common pitfalls

**Non-determinism creeping into the engine.** Iterating over a set of strings (hash randomization), floats in game state, the module-level `random`, reading the clock. Each one is a lint rule or a test, not a code-review hope.

**Fog-of-war leaks through side channels.** Sequential unit ids reveal how many units the enemy has spawned. An error message mentions a hidden unit. An event log reports an attack from out of sight. The property test catches leaks in the state; side channels need a review of every observation field.

**Seat bias in simultaneous resolution.** "Process seat 0's moves first" sneaks in through a loop. The seat-swap mirror test is the guard.

**Treating Pyodide as a sandbox.** `import js` reaches the host runtime. WASM is one layer, not the boundary.

**Trusting anything the bot reports.** The harness runs inside the jail, so its timings, turn numbers and message framing are all attacker-controlled.

**Wall-clock limits on a shared VM.** Noisy neighbours cause unfair timeouts. Charge CPU time and keep the wall clock only as a backstop.

**Rating the platform's failures.** A worker crash recorded as a loss quietly corrupts the ladder. A platform error always voids the match.

**Ranking by μ.** A bot that won its one game sits at the top. Rank by the conservative score and show provisional status.

**Self-play Elo inflation.** The boss looks like it improves forever against itself. Only fixed baselines measure real progress.

**Replays that depend on bot code.** If a replay needs the bots to be re-run, it breaks the first time a bot reads the clock. Store orders.

**Rule changes without a version bump.** Old replays stop re-simulating and old ratings stop meaning anything. Engine version plus seasons.

**Free tiers quietly changing.** Terms move under you. Date every check, and keep the stack small enough to move to another provider in a day.

**Unbounded storage.** Logs and frame caches grow until the free disk is full. Every store gets a cap and a retention rule.

**Sybil farming.** A user uploads throwaway bots that lose to their main bot. Same-owner exclusion plus per-user caps.

**Strategy leaking through public logs.** Opponents read your debug output in a public replay. Logs are owner-only.

---

## Tech stack summary

| Layer | Tool | Why |
|---|---|---|
| Game engine | Pure Python, zero deps, integer-only | One implementation for CLI, browser, server and RL |
| Bot runtime (browser) | Pyodide in Web Workers | Practice costs the server nothing |
| Bot sandbox (server) | Decided in ADR-002: Pyodide-in-Deno or CPython in nsjail/gVisor, always inside an OS jail | Hostile code on a shared box |
| API | FastAPI + uvicorn (websockets included) | Typed schemas, async fan-out, same language as the engine |
| Database & queue | SQLite (WAL) | One server, one file, nothing extra to operate |
| Ratings | OpenSkill (Weng–Lin), per ADR-003 | Per-match μ/σ updates, open license |
| Backups | Litestream + rclone → free object storage | Continuous, restorable, free |
| Frontend | SvelteKit (static) + Canvas 2D + CodeMirror 6 | Static hosting, small bundle |
| Auth | GitHub OAuth | Free, and the audience already has accounts |
| TLS / proxy | Caddy | Automatic certificates |
| RL | PyTorch (training only), PettingZoo, numpy inference | The boss ships without a torch dependency |
| CI/CD | GitHub Actions | Free for public repos |
| Code quality | ruff, pyright, import-linter, pytest + hypothesis, Playwright | `make verify` as the single entry point |
| Dependency management | uv (workspace), npm | Pinned and reproducible |

---

### Suggested CV line
> *Built Bot Arena, a public programming game where players' Python bots compete on a ranked ladder: a deterministic simultaneous-move engine shared by the browser (Pyodide) and the server, hardened sandboxing for untrusted code (adversarial test suite, zero platform failures over X matches), OpenSkill ratings with calibrated confidence ranges, live websocket spectating, and a self-play RL boss with a model card, all running at zero cost. Y players, Z bots, W matches per day.*
