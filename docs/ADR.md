# Architecture Decision Record

Decisions that are expensive to reverse, recorded with the reasoning that produced them. Each entry states the alternatives considered and what would make us change our mind. An ADR that only names the winner is a press release, not a record.

A decision that changes gets a new entry that supersedes the old one. Old entries are never rewritten.

---

## ADR-001 — One deterministic engine, in pure Python, shared everywhere

**Status:** accepted · **Date:** 2026-11-25

### Context

The game is 1v1, simultaneous-move, on a grid with fog of war. Four places need to run it: the players' local CLI, browser practice (Pyodide), the ranked match workers, and RL training. Replays, fair version comparisons, rating audits and debugging all assume that a match is fully determined by its seed and its order stream.

### Decision

- There is **one engine**: a pure-Python package (`engine/`, imported as `arena_engine`) with **zero runtime dependencies**, used unchanged in all four places. The rules are never reimplemented in TypeScript or anywhere else.
- The engine is **pure**. It does no I/O and reads no clock, environment or global state. Its only randomness is a `random.Random(seed)` instance passed in explicitly. It uses integer arithmetic only.
- **The workspace targets Python 3.14**, the version that ships with Pyodide 314.0.8 (Python 3.14.2, released 2026-11-13). The browser and the server must run the same language version. Bumping Pyodide is a deliberate change of its own.

### Reasoning

A second implementation of the rules (say, a TypeScript one for the browser) would be a permanent source of divergence that only shows up as "my bot behaves differently in ranked". Python lets the engine run inside Pyodide in the browser with no port. Zero dependencies keep Pyodide start-up cheap and leave nothing for a sandboxed bot to exploit through the engine.

Purity is enforced by checks, not by convention. Ruff's `banned-api` in `engine/pyproject.toml` rejects clocks, I/O, concurrency and module-level `random`. An AST test in `tests/test_guardrails.py` rejects `hash()`, `id()`, `open()` and `input()`, which ruff cannot see. An import-linter contract stops the engine from importing the rest of the repo.

### Alternatives considered

- **A Rust or C engine compiled to WASM for every runtime.** Faster, and one artifact. But it splits the codebase across two languages before speed has been shown to matter, and players (who write Python) could no longer read the reference rules as code.
- **Separate engines for the browser and the server.** Rejected for the divergence reason above.
- **Floats in game state.** Rejected. Integer-only state is trivially identical across CPython, Pyodide and any future batched implementation.

### What would change our mind

If RL training (Phase 11) is limited by engine speed even after profiling, a batched engine for training only becomes acceptable. It must be proven equal to the reference engine by differential tests on recorded replays, and the reference engine stays the only one used for rated play.

---

## ADR-002 — CPython in bubblewrap, behind seccomp and cgroups, for ranked matches

**Status:** accepted · **Date:** 2026-11-26 · **Spike:** Linux arm64, Docker Desktop on Apple M5

### Context

Ranked matches run strangers' Python on our only server. The sandbox must contain CPU, memory, processes, filesystem and network. It must let the host measure each bot's CPU time per turn. And ideally a bot should behave on the server exactly as it does in browser practice.

ADR-005 makes the target concrete: an ARM64 VM with **2 OCPUs and 12 GB of RAM**, which leaves one core for matches. Every millisecond and megabyte of per-bot overhead comes straight out of match throughput.

### Measurements

The spike drove each candidate through the real `ProcessChannel` and harness, running a bot that holds still (start-up and protocol overhead) and a bot that does 14 full-map BFS runs per turn (Python speed).

| Candidate | Cold start | Overhead per turn | Peak memory per bot | Python speed |
|---|---|---|---|---|
| B. CPython in bubblewrap | **23 ms** | 0.04 ms | **20 MiB** | **13.5 ms/turn** |
| A. Pyodide 314.0.8 in Deno, in bubblewrap | 942 ms | 0.09 ms | 218 MiB | 35.0 ms/turn |
| CPython, no jail (reference) | 28 ms | 0.04 ms | 20 MiB | 13.6 ms/turn |

The jail itself costs nothing measurable. Pyodide costs 40× the start-up, 11× the memory and 2.6× the CPU for the same Python.

### Decision

Ranked bots run as **CPython 3.14 inside bubblewrap**, one fresh jail per bot per match. The layers:

- **Namespaces** (`--unshare-all`): no network, its own PIDs, IPC and hostname, and a user namespace that maps the bot to `nobody` with every capability dropped.
- **Filesystem:** read-only `/usr` and the arena virtualenv, the bot's own file and nothing else, plus a size-capped tmpfs at `/tmp`. The environment is cleared.
- **seccomp:** a deny-list in `sandbox/seccomp_policy.py`, compiled to BPF at image build. It blocks kernel-admin and namespace syscalls, `ptrace` and cross-process memory access, `io_uring`, `bpf`, `perf_event_open`, keyrings, every socket family except Unix sockets, and `clone` with namespace flags. `clone3` gets `ENOSYS` so libc falls back to `clone`, whose flags seccomp can inspect.
- **cgroup v2, one per bot:** `memory.max` with swap off (a memory bomb is OOM-killed and recorded as `memory`), `pids.max` (fork and thread bombs hit a wall), and `cpu.max` of one core. `cpu.stat` gives the host each turn's CPU time. `cgroup.kill` ends the match and leaves no stragglers. The bot joins its cgroup *before* `exec`, so even import-time code is contained.
- **Host-side time:** CPU per turn from `cpu.stat`, a time bank, and a wall-clock backstop for bots that sleep.

### Reasoning

On a 2-core box, CPU is the scarce resource. A would spend about 2 s of start-up per match, give every bot 2.6× less work per millisecond of budget, and use ten times the memory. B keeps players' local CLI runs (CPython) and ranked matches on the same interpreter, so local timing warnings mean something.

What A offered was a WebAssembly layer underneath the OS jail. B replaces it with a syscall filter and resource limits. That's the same family of defences container runtimes and Flatpak use, and the adversarial suite (`sandbox/adversarial/`) exercises it on every CI run.

### Alternatives considered

- **A. Pyodide in Deno inside the same jail.** Stronger defence in depth, and the same runtime as browser practice. Rejected on cost, as measured above. Browser practice already labels its timing as indicative, because a player's machine isn't the server either.
- **C. gVisor (`runsc`).** A user-space kernel is the strongest of the three. It wasn't measured: it needs a custom Docker runtime that Docker Desktop doesn't readily allow. It also adds an operational layer to a one-person, one-VM deployment, and its syscall interception costs CPU we don't have.
- **nsjail instead of bubblewrap.** Similar layers with built-in cgroup and seccomp support, but it has to be built from source. bubblewrap is packaged in Debian and Ubuntu, and the cgroup and seccomp pieces are small.

### What would change our mind

- A kernel escape that the seccomp policy can't close.
- Running on hardware where CPU is cheap.
- A need for numpy-heavy bots whose behaviour differs between CPython and Pyodide.

Any of these would bring back A or C. The runner launches a bot from an `argv`, so switching jails means changing that launch command; the protocol and harness stay as they are.

---

## ADR-003 — OpenSkill (Weng–Lin) for ratings

**Status:** accepted · **Date:** 2026-11-25

### Context

The ladder has to say how sure it is. "A is stronger than B with 87% confidence" needs a skill estimate *and* its uncertainty for every bot. Matches finish one at a time, continuously, so ratings should update after each one. Ratings must also be rebuildable from the results log, so the system has to be a deterministic function of an ordered list of results.

### Decision

Use **OpenSkill's Weng–Lin model** (`openskill` on PyPI: MIT-licensed, v6.2.0, last release January 2026). Each bot version gets a Gaussian skill estimate (μ, σ). The leaderboard ranks by the conservative score μ − kσ. The package is added to `server` in Phase 5, when it is first used.

### Reasoning

Weng–Lin is a Bayesian approximation in the same family as TrueSkill. It updates after every game and keeps an explicit σ, so P(skill A > skill B) = Φ((μA − μB) / √(σA² + σB²)) can be read straight off the ratings. It is open, small, and pure Python.

### Alternatives considered

- **TrueSkill.** The best-known option with the same μ/σ shape, but Microsoft holds the patents and trademark. Fine for a hobby project, yet an unnecessary question mark when an open equivalent exists.
- **Glicko-2.** Also has uncertainty (the rating deviation), but it is designed around rating periods that batch games. Per-match updates are possible but go against its design.
- **Elo.** No uncertainty, so it can't make the confidence statements this project is built around.
- **Bradley–Terry fitted offline in batch.** Excellent for ground truth, and Phase 5 uses it exactly that way to validate the live system. Too slow and too global to refit after every match.

### What would change our mind

If the Phase 5 synthetic-ladder validation shows OpenSkill is miscalibrated in a way that tuning β and τ can't fix, or if the package is abandoned. Because ratings are rebuilt from the results log, switching systems means a rebuild, not a migration.

---

## ADR-004 — SQLite is the database and the queue

**Status:** accepted · **Date:** 2026-11-25

### Context

Everything runs on one small VM. We need to store users, bots, versions, matches, results and derived ratings, plus a work queue that a few worker processes claim matches from.

### Decision

One SQLite database in **WAL mode**. The match queue is a table. A worker claims a match with a single `UPDATE … RETURNING` inside `BEGIN IMMEDIATE`, and a lease column with a reaper handles dead workers. Migrations are plain SQL files applied in order. Backups stream continuously to object storage (ADR-005).

### Reasoning

At our scale (one machine, a handful of writers, writes measured in matches per minute) SQLite has the lowest operational cost: no daemon, no network hop, and a backup is a copy of one file. WAL mode lets the API read while workers write. A table-backed queue gets transactional claims for free and keeps queue state in the same backup as everything else.

### Alternatives considered

- **Postgres.** More concurrency headroom, but it's another service to run, tune, secure and back up on a 12 GB box, and free managed tiers bring their own limits and expiry rules.
- **Redis or Celery for the queue.** Two more moving parts to solve a problem one indexed table already solves.

### What would change our mind

Measured write contention: queue claims or result writes waiting on locks often enough to hurt throughput. Or a move beyond one machine.

---

## ADR-005 — Hosting: one free-tier VM, free static hosting, free object storage

**Status:** accepted · **Date:** 2026-11-25 · **Terms last checked:** 2026-11-25

### Context

Running cost must be zero (see CLAUDE.md). Free tiers change without much notice, so this ADR records the terms as they were on the date above. Re-check them before relying on them (Phase 9) and whenever something looks off.

### Decision

| Role | Choice | Terms on 2026-11-25 |
|---|---|---|
| Server VM | **Oracle Cloud Always Free, Ampere A1 (ARM64)** | **2 OCPUs and 12 GB memory in total** (1,500 OCPU-hours and 9,000 GB-hours per month), as one or two instances; 200 GB block storage; 10 TB/month outbound. *Halved from 4 OCPUs / 24 GB; community reports date the change to 18 Aug 2026.* |
| Static frontend | **Cloudflare Pages** (Free) | 20,000 files per site; 25 MiB per file; 500 builds/month; builds time out after 20 min |
| Object storage (backups) | **Cloudflare R2** (Free) | 10 GB-month Standard storage; 1M Class A (write/list) and 10M Class B (read) operations/month; no egress fees |
| CI/CD | **GitHub Actions** | Standard GitHub-hosted runners are free for public repositories; larger runners are billed even for public repos, so we don't use them |
| Pyodide delivery | **jsDelivr CDN** (Pyodide's official distribution) | Pyodide is loaded from the CDN, not served by us |

### Consequences we design for

- **Capacity:** with 2 cores and one kept for the API, there is **one match worker**. Phase 3's per-match CPU cost directly sets the daily match cap (Phase 9). That makes the sandbox's per-bot overhead an ADR-002 criterion.
- **Idle reclamation:** Oracle may reclaim an Always Free instance if, over 7 days, **95th-percentile CPU, network and (for A1) memory utilisation are all below 20%**. A ladder playing matches is real load. A ladder that goes quiet could be reclaimed. We don't burn CPU to look busy. The defense is continuous backups and a restore drill that has been tested (Phase 9).
- **R2 operation budget:** a backup tool that uploads a WAL segment every second makes about 2.6M PUTs a month, more than double the free 1M Class A operations. Litestream's sync interval must be set so monthly uploads stay well under the cap (every 10 s ≈ 260k).
- **Cloudflare Pages per-file cap:** fine, because Pyodide (whose WASM is the only large file) comes from the CDN.

### Alternatives considered

- **GitHub Pages** for the frontend: 1 GB site, 100 GB/month soft bandwidth limit, no commercial SaaS use. A good fallback, and Bot Arena is non-commercial. We prefer Cloudflare Pages because R2 already needs a Cloudflare account.
- **Oracle's AMD micro instances** (2 × 1/8 OCPU, 1 GB each, 50 Mbps): too small to run sandboxed Pyodide bots.
- **Paid VMs from about €4/month.** That breaks the zero-cost constraint. It's the fallback if Always Free becomes unusable, and the single-VM design means moving is a restore drill, not a redesign.

### Still to check (not needed before Phase 9/10)

- **Uptime monitoring:** sources conflict on UptimeRobot's free plan (reportedly 50 monitors at 5-minute intervals, possibly non-commercial only) and say little about healthchecks.io. Decide in Phase 10 from the providers' own terms pages.
- **Free notebook GPUs for RL training:** check in Phase 11.
- **Domain:** optional. A free `*.pages.dev` subdomain works, and a custom domain is the only cost we'd knowingly accept.

### What would change our mind

Oracle cutting Always Free again, reclaiming our instance, or ARM capacity being unavailable in our home region. Any of these moves the server to the cheapest paid VM, recorded as a new ADR with the cost stated.

### Sources (read 2026-11-25)

- Oracle: [Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/resourceref.htm); [InfoQ on the A1 limit cut](https://infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)
- Cloudflare: [Pages limits](https://developers.cloudflare.com/pages/platform/limits), [Pages file-limit changelog (2026-01-23)](https://developers.cloudflare.com/changelog/2026-01-23-pages-file-limit-increase/), [R2 pricing](https://developers.cloudflare.com/r2/pricing)
- GitHub: [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [Actions pricing changelog (2026-01-01)](https://github.blog/changelog/2026-01-01-reduced-pricing-for-github-hosted-runners-usage/), [Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)

---

## ADR-006 — Frontend: SvelteKit (static), Canvas 2D, CodeMirror 6

**Status:** accepted · **Date:** 2026-11-25

### Context

The frontend is a static site (ADR-005) with a handful of pages: ladder, bot pages, docs, stats. It has one demanding component, the match viewer, which renders up to hundreds of turns with a scrubber, plus a code editor for browser practice.

### Decision

**SvelteKit** with `adapter-static` (every route prerendered) and TypeScript in strict mode. The viewer draws on a **Canvas 2D** context. The practice editor is **CodeMirror 6**. Linting is ESLint plus Prettier, and tests use Vitest. `svelte-check`, `eslint`, `prettier --check` and `vitest` run in `make verify`. Node 26 LTS in CI (`web/.nvmrc`), 24+ supported.

### Reasoning

Svelte compiles to small bundles with little boilerplate, which matters for a solo project where the frontend isn't the point. A Canvas board scales to a 32×32 grid with many units, where a DOM element per cell gets sluggish while scrubbing. CodeMirror 6 is much lighter than Monaco and has good Python support.

### Alternatives considered

- **React + Vite.** The bigger ecosystem and stronger CV signal. A reasonable choice; we passed on it for bundle size and boilerplate.
- **Plain TypeScript, no framework.** Fine for the viewer alone, but routing, data loading and the static build would all be hand-rolled.
- **Monaco editor.** Heavier, and the VS Code feel isn't needed for single-file bots.

### What would change our mind

If the viewer or the practice mode needs a library that only exists for React, or if CV recognition starts to matter more than footprint.

---

## ADR-007 — Replays store orders; viewer frames are derived

**Status:** accepted · **Date:** 2026-11-25

### Context

Every match needs a replay: to watch it, to debug it, to re-check its result before rating, and to rebuild history after a rules or rating change. Bots are not deterministic in general. A bot can read the clock, and timeouts depend on load.

### Decision

The canonical replay is **seed + match config + engine version + the per-turn orders of both bots + outcome + final state hash**, stored as gzipped JSON and content-addressed by sha256. Viewer frames (state deltas and per-seat visibility) are **derived** from it by running the engine, then cached; they can be deleted and regenerated. Bot logs are stored separately, are visible only to the bot's owner, and are size-capped.

### Reasoning

Replaying from orders needs no bot code. That works for bots that read the clock, bots that have since been deleted, and code that is private. Orders are a few KB per match. Re-simulating from orders and comparing the final hash is a cheap integrity check before a result is rated. Recording the engine version means an old replay is always re-simulated with the rules it was played under.

### Alternatives considered

- **Seed plus bot versions only.** Too fragile: any non-deterministic bot or a timeout makes it impossible to reproduce.
- **Full state snapshots every turn as the canonical form.** Simple to view, but tens of times larger, and it loses the "re-simulate to verify" property.
- **A binary encoding.** Smaller still, but premature. Gzipped JSON is readable, debuggable, and small enough for the R2 free tier.

### What would change our mind

Replay storage threatening the free storage cap (then a binary encoding), or a need to replay without the engine (then frames become canonical too).
