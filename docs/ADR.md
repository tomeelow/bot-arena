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

**Status:** superseded in part by ADR-010 (the VM, backups and how the site reaches the API) · **Date:** 2026-11-25 · **Terms last checked:** 2026-11-25

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

---

## ADR-008 — Rating parameters chosen on a synthetic ladder

**Status:** accepted · **Date:** 2026-11-26 · **Refines:** ADR-003

### Context

ADR-003 chose OpenSkill. Before players rely on its numbers, `scripts/ratings_validation.py` runs the real matchmaker, worker and live ratings over 17 bots whose true order is known. The bots are the built-ins at noise 0, 0.25, 0.5 and 0.75, plus random, and the truth is a round robin fitted with Bradley–Terry. The targets were fixed in the script before the first run.

### What the runs showed

| Check (target) | Run 1: OpenSkill defaults | Run 2: this ADR, fresh seeds |
|---|---|---|
| Kendall τ at 50 games per bot (≥ 0.90) | 0.882 | 0.868 |
| Worst calibration gap of P(win) (≤ 0.10) | 0.163 | 0.108 |
| Worst gap of "X% stronger" vs truth (≤ 0.15) | 0.067 | 0.016 |
| Median games until σ < 3.0 (≤ 50) | not reached in 60 | not reached in 60 (σ ≈ 3.1) |

Run 1 had two problems:
- **Predictions were underconfident:** a predicted 65–75% won 81–88% of the time.
- **Games were wasted:** 44% of them were near-certain blowouts, which carry almost no information.

### Decision

- **β = 3.0**, down from 4.17. This is the per-game noise term: our games are more decisive than OpenSkill's default assumes. The value was picked by prequential log loss over run 1's recorded results, sweeping β from 1 to 4.17 (best: 2.5–3.0). Smaller values overshoot into overconfidence.
- **Exploration floor 0.02**, down from 0.1, so the matchmaker mostly picks informative, close games.
- **τ = 0** stays. A version's code, and so its skill, never changes.

### What is still missed, and why it isn't hidden

- **Ordering (τ 0.87–0.88).** Most inversions are near-ties in the truth, around 55–60% matchups. The game is also deliberately intransitive (rush beats greed, greed beats turtle, turtle holds rush), so no single number orders those bots the same way for every opponent mix. The round robin and the matchmaker face different mixes.
- **Convergence.** σ reaches about 3.1 at 50–60 games. Leaving "provisional" takes roughly 60–70 games, not 50.
- **The targets stay as they were.** The open item in the plan's Phase 5 tracks them. The next things to try are a wider prior σ (the population's μ spread is about twice the default prior) and more ladder games per check.

### What would change our mind

Real ladder results that calibrate worse than this synthetic one would. So would a fix that meets the τ and convergence targets on fresh seeds without hurting calibration.


---

## ADR-009 — Browser practice drives the CLI's match loop from JavaScript

**Status:** accepted · **Date:** 2026-11-26 · **Refines:** ADR-001, ADR-006

### Context

Phase 8 runs practice matches in the browser, and their replays must equal the CLI's for the same seed and bots. The CLI's `run_match` is synchronous: it sends each bot a line, then blocks until the reply arrives or the backstop passes. In a browser the player's bot has to run in its own Web Worker, so a hung bot can be terminated, and Python in one worker can't block waiting on another without extra machinery.

### Decision

- **The match loop has no I/O.** `arena.runner.Match` says what to send each bot and is told what each one replied. `run_match` drives it over channels (local and ranked), and browser practice drives it from JavaScript. The rules, the checks on replies and the record are one piece of code.
- **There are two workers per practice match.** The host worker runs the engine, `Match` and the built-in opponent (`arena.practice.Practice`). The player worker runs the player's code behind the CLI's harness (`arena.practice.PlayerBot`). The page carries the protocol lines between them and owns the backstop timer. A bot that misses it has its worker terminated and loses on time, with the CLI's wording.
- **Assets come from our own origin.** The pinned Pyodide runtime and the Python sources are copied into the static build (`web/scripts/practice-assets.mjs`). No CDN is involved, and the page's CSP stays `'self'`.
- **The editor lives in a shadow root.** CodeMirror then puts its styles in a constructed stylesheet, which the strict CSP allows. In the document it would need an inline `<style>`, which the CSP blocks.

### Alternatives considered

- **Blocking with SharedArrayBuffer and `Atomics.wait`.** This needs cross-origin isolation (COOP/COEP headers), which not every free static host can set, and it keeps a second copy of the loop's timing logic.
- **JSPI (`run_sync`).** It lets Python await JavaScript synchronously, but browser support is still uneven.
- **Reimplementing the loop in TypeScript.** That breaks "one engine, one protocol" (CLAUDE.md).
- **Loading Pyodide from a CDN.** That would mean a third-party script origin in the CSP and a dependency on someone else's uptime.

### Consequences

- `tests/e2e/practice.spec.ts` (Playwright) checks that the downloaded practice replay equals the CLI's for the same seed and bots, ignoring thinking times and the bot's file path. It also checks that a hung bot is stopped while the page keeps responding.
- The static build carries about 13 MB of Pyodide runtime.

### What would change our mind

Broad JSPI support could let the host call the player synchronously and drop the page relay. A host that can't serve `.wasm` from our origin would push us towards a CDN, with its origin pinned in the CSP.

---

## ADR-010 — Hosting on a Google Cloud e2-micro, behind a Cloudflare Pages proxy

**Status:** accepted · **Date:** 2026-11-26 · **Terms last checked:** 2026-11-26 · **Supersedes:** ADR-005's VM, backup and topology choices

### Context

Oracle's Always Free A1 shape (ADR-005) can't be had in practice: the owner tried, and free-tier ARM capacity was never available. AWS has no always-free VM for new accounts: credits, then a bill. Google Cloud's free tier still includes a small VM with no end date. Its limits differ from Oracle's in ways that shape the design:

| Google Cloud Free Tier, read 2026-11-26 | Limit |
|---|---|
| VM | 1 non-preemptible **e2-micro** a month (counted in hours) in `us-west1`, `us-central1` or `us-east1` |
| CPU and memory | 2 shared vCPUs at **12.5% each, 25% of a core sustained**; **1 GB** RAM |
| Disk | **30 GB-months of standard** persistent disk (balanced and SSD disks are billed) |
| Egress | **1 GB a month** from North America to all destinations except China and Australia |
| External IP | not charged for the free-tier instance |
| Cloud Storage | 5 GB-months regional storage (same three regions), 5,000 Class A and 50,000 Class B operations a month |
| Terms | "no end date", but may change on 30 days' notice; a billing account is required; usage past the limits is billed |

| Cloudflare, read 2026-11-26 | Limit |
|---|---|
| Pages static requests | free and unlimited |
| Pages Functions | count against Workers Free: **100,000 requests a day**, then error 1027 (a hard stop, not a bill); 10 ms CPU per request |

**The scarce resource is egress, not CPU.** Serving the site from the VM would spend the 1 GB on the 13 MB Pyodide runtime within about 75 first visits.

### Decision

- **Cloudflare Pages serves the site.** That covers the static build, Pyodide and `static/_headers` (security headers, plus the practice workers' CSP, which allows `'wasm-unsafe-eval'`).
- **A Pages Function proxies `/api`, `/auth` and `/ws` to the VM.** It lives in `web/functions/` and `web/src/proxy.ts`. The browser sees one origin (`*.pages.dev`), as the SameSite session cookie and the relative API calls require. The function adds a shared secret, and the VM's Caddy refuses any request without it. `/health` is the one exception.
- **The VM is one e2-micro running Debian 13.** Caddy uses a free DuckDNS subdomain for TLS. systemd runs `arena-api`, one `arena-worker@1`, `arena-scheduler`, and timers for `ops guard` (every 5 minutes) and `ops backup` (hourly).
  - Python 3.14 comes from uv, installed under `/usr`, which the jail already mounts read-only. The jail is unchanged.
  - The worker's cgroup is delegated by systemd (`Delegate=`, `DelegateSubgroup=main`), and `deploy/jail-cgroup.sh` gives the jails a sibling `bots/` subtree. The worker runs as an unprivileged user. A non-root jailed match and a memory bomb were checked in a Debian 13 container with exactly this layout, and the units pass `systemd-analyze verify` on systemd 257.
- **Backups go to a Cloud Storage bucket in the VM's region, not R2.** Same-region traffic isn't billed as egress, and the VM signs in as its own service account, so there's no storage secret to keep.
  - Every hour, `ops backup` uploads a `VACUUM INTO` snapshot of the database, but only if it changed, and at least once a day.
  - Alongside it goes one tar of the code and replay files added since the last run. They're content-addressed, so new files are the only change.
  - That's at most about 1,500 Class A operations a month. Litestream is not used: continuous WAL shipping would spend the 5,000 monthly operations in days.
- **The budget guard enforces the egress limit.** `ops guard` reads the default interface's transmit counter, minus what backups uploaded. Once `egress_month_bytes` (800 MB) has gone out in the calendar month, it writes `EGRESS_CAPPED`, and Caddy answers 503 until the 1st. The same guard pauses the ladder when the disk is 85% full, and expires bot logs (14 days) and live frame files (7 days).
- **The kill switch is a file.** `ops pause` writes `PAUSED`: workers run no bot code and the scheduler queues nothing. Queued matches stay queued, and `ops resume` picks them up again.

### Capacity budget

- **CPU, not binding.** Phase 3 measured ≈ 0.4 CPU-s per match on the dev machine. Allow 2× for the slower shared core, and give matches 0.2 of the 0.25 sustained core at 50% target utilisation. That's 0.2 × 86,400 × 0.5 / 0.8 ≈ **10,800 matches a day**. The VM measurement replaces the dev number once it's taken.
- **Backup storage, binding.** A stored replay is about 5.4 KB gzipped (median of 145 dev replays). At 1,000 matches a day that's about 2 GB a year, against 5 GB free with room left for snapshots. So **`matches_per_day = 1000`**, in `server/src/arena_server/settings.toml`. Placements and comparisons count towards it.
- **Memory.** Two bots at 256 MiB plus the worker fit under the worker unit's 640 MB `MemoryMax`. The API (250 MB) and scheduler (150 MB) have their own caps. A 1 GB swap file serves everything except the jails, which have swap turned off.
- **Egress.** Viewing a replay downloads its frames: about 19 KB gzipped (median), or about 350 KB uncompressed over the live websocket. That's roughly 40,000 replay views or 2,000 live views on 800 MB. Pages Functions' 100,000 requests a day is a second hard stop in front of it.

### Alternatives considered

- **Serving everything from the VM.** Simplest, but the egress would run out as soon as anyone used it.
- **The API on its own origin, with CORS.** A `*.pages.dev` site and a `*.duckdns.org` API aren't the same site, so the `SameSite=Lax` session cookie wouldn't be sent. Making it work needs `SameSite=None` cookies and CSRF tokens, or a paid domain.
- **Cloudflare Tunnel instead of a public port.** A named tunnel needs a domain on Cloudflare (a cost). Quick tunnels have random, temporary names.
- **Litestream to R2.** Every WAL upload from the VM counts as egress, and that adds up fast.
- **Running the CI sandbox image under Docker on the VM.** It's the exact image the adversarial suite runs in, but dockerd costs memory a 1 GB VM can't spare, and the container would have to run privileged, with the worker as root inside it.
- **AWS:** free for about 6–12 months on credits, then billed. **Oracle:** capacity was never available.

### Risks to watch

- **Shared-core timing.** The host measures a bot's thinking as CPU time, but the 2 s wall-clock backstop runs in real time. On a quarter of a core, a turn that draws heavily on the time bank could hit the backstop without being over its CPU budget. Measure the wall-to-CPU ratio on the VM first. A fix would change how timeouts count, which is a rule change that needs asking first.
- **The ephemeral IP changes if the VM is stopped and started** (not on reboot). DuckDNS then has to be updated (RUNBOOK).

### What would change our mind

- Google changing the e2-micro terms.
- Sustained egress or CPU above the budgets.
- Any bill above €0.

The next step is the cheapest paid VM, recorded as a new ADR with its cost. The single-VM design and the restore drill make that a move, not a redesign.

### Sources (read 2026-11-26)

- Google: [Free cloud features](https://docs.cloud.google.com/free/docs/free-cloud-features), [vCPUs on shared-core machines](https://docs.cloud.google.com/docs/compute-area/vcpus), [E2 machine types (blog)](https://cloud.google.com/blog/products/compute/google-compute-engine-gets-new-e2-vm-machine-types), [external IP pricing](https://cloud.google.com/vpc/pricing-announce-external-ips)
- Cloudflare: [Pages Functions pricing](https://developers.cloudflare.com/pages/functions/pricing/), [Workers limits](https://developers.cloudflare.com/workers/platform/limits/), [Pages limits](https://developers.cloudflare.com/pages/platform/limits)

---

## ADR-011 — Alerts as a dead man's switch at Healthchecks.io

**Status:** accepted · **Date:** 2026-11-26 · **Terms last checked:** 2026-11-26 · **Settles:** ADR-005's open question on uptime monitoring

### Context

Phase 10 needs free email alerts when a platform error occurs, the disk passes 80% or the queue backs up. It also has to alert when the VM itself is down, which a VM can't do for itself. Sending email from the VM needs an SMTP account. An uptime checker that polls a public URL would also need the VM to publish its alerts.

### Decision

**Healthchecks.io's free Hobbyist plan** ($0; 20 checks; read 2026-11-26), used as a dead man's switch:
- `ops guard` already runs every 5 minutes. It now also computes the health alerts (`metrics.alerts`).
- With no alerts, it pings the check's URL. With alerts, it pings `<url>/fail` with the reasons in the body.
- Configure the check with a 5-minute period and a 10-minute grace time. Then a VM that is down, a dead timer, or a broken guard all alert by missing their pings.

The ping URL sits in `/etc/arena/alerts.env`. Without it, the guard sends nothing.

### Alternatives considered

- **UptimeRobot polling a `/health/alerts` endpoint.** That publishes the alert reasons to anyone, and sources still conflict on whether the free plan allows non-personal use (ADR-005).
- **Email from the VM.** It needs an SMTP provider and its credentials, and it can't report its own outage.
- **Google Cloud Monitoring alerts.** The VM would need an ops agent to report disk usage, which costs memory a 1 GB machine can't spare. It also ties alerting to the project it watches.

### What would change our mind

Healthchecks.io limiting free checks or email alerts. Its code is open source (BSD), so self-hosting it somewhere free is the fallback.

### Sources (read 2026-11-26)

- [Healthchecks.io pricing](https://healthchecks.io/pricing)

---

## ADR-012 — The RL boss: a learned strategy over shared tactics, trained with numpy PPO, shipped as pure Python

**Status:** accepted · **Date:** 2026-11-26 · **Departs from:** the Phase 11 plan's per-cell action map, PyTorch and pure-numpy inference

### Context

The plan sketched a per-cell action map over grid channels, a small convolutional net trained with PyTorch, and a pure-numpy forward pass in the shipped bot. Two facts changed that:

- **numpy is not in the jail.** Ranked bots get the standard library and the starter kit. Adding numpy would change the jail's allowed modules, which CLAUDE.md lists under "Ask before acting", and it would grow the read-only venv that every jail binds.
- **Compute is one laptop.** The engine is pure Python, at about 0.15–0.3 s per 400-turn match. A per-cell policy would have to learn moving, mining and fighting from a win/loss signal, which needs far more games than that budget allows.

### Decision

- **What the network decides.** Every 4 turns a two-layer MLP (64 tanh units, 6,664 parameters) picks what the Core builds (nothing, a worker, a soldier or a scout) and the soldiers' stance (defend a ring at home, attack the enemy Core, or hunt the enemy units seen last). Workers, pathing and adjacent fights use `arena.builtin.tactics`, the same code the scripted bots use. The network sees 30 scaled features of the observation and of the bot's memory of earlier ones (`rl/src/arena_rl/boss.py`).
- **Training.** PPO with hand-written gradients in numpy (`ppo.py`; a test checks them against finite differences), against a league: the scripted bots weighted towards the strong ones, past checkpoints, and the current policy. The reward is the result alone: +1, 0 or −1.
- **Environment.** Our own two-seat environment, shaped like a PettingZoo `ParallelEnv` but without the dependency (`env.py`). It uses the engine's `observe()` and seeds each bot as the harness does. A test checks that it gives the CLI runner's result and final state, bit for bit.
- **Shipping.** The bot is one pure-Python file: `boss.py` with the weights written in by `export.py`. It imports only the starter kit and the standard library, and a test enforces that. It is uploaded with `ops upload-boss` under an `arena-boss` account, as a pending version that goes through the same size cap, smoke match, jail, limits and placement as anyone's upload.
- **Packaging.** `rl/` is its own uv project, not a workspace member, so the server's `uv sync --all-packages` never installs numpy. `make verify` runs its types and tests (`rl-check`), and a guardrail test keeps it out of the workspace.

### Alternatives considered

- **The per-cell convolutional policy from the plan.** It is the more general learner, but there is no affordable way to train it here. It would also need numpy in the jail, or a pure-Python convolution at 1,024 cells a turn, against a 100 ms budget.
- **numpy in the jail.** It would make a pure-numpy forward pass possible. But it is a sandbox change made for one bot, and every bot would get it, which is a UX change too. Pure Python is fast enough: the boss's p99 think time in the jail is a few milliseconds.
- **PyTorch for training.** It would save the hand-written gradients, but it is a large dependency for a 6k-parameter MLP, and the gradient test already covers the risk.
- **Behaviour cloning from the scripted bots first.** It wasn't needed: PPO from scratch learned to beat rush within minutes of laptop time. Turtle needed better features, not a better start (docs/boss_model_card.md).

### What would change our mind

The boss plateauing below the best human bots for good: then a richer action space (per-unit targets) is worth the compute, starting with behaviour cloning. Also numpy being added to the jail for players' own sake, which would make larger networks cheap to ship.

## ADR-013 — The Arcade visual theme: dark only, with self-hosted fonts

**Status:** accepted · **Date:** 2026-11-27

### Context

The frontend shipped with system fonts and a neutral palette that followed the OS between light and dark. We compared a dozen themes as static mockups and picked "Arcade": a dark plum ground, Bungee capitals for page titles and big figures, Chivo for reading, hard zero-blur offsets on anything you can press, ember as the lead colour and acid yellow as the answer. Two constraints shape how it ships:

- **Every request stays on our origin.** The CSP has `font-src 'self'`, and `tests/e2e/privacy.spec.ts` fails if any page talks to another origin, so Google Fonts' CDN is out.
- **The theme only works dark.** Its contrast and the colour split on titles depend on the dark ground; a light version would be a different design.

### Decision

- **Dark only.** `color-scheme: dark`, one set of tokens in `web/src/app.css`. Every colour and font is a token there; components only use tokens.
- **Fonts from `@fontsource/bungee` and `@fontsource-variable/chivo`,** pinned (5.3.0, SIL OFL 1.1). Vite bundles their woff2 files into the build, so they are served from our origin like any other asset. No third-party request, no CSP change.
- **Big figures use Bungee, not a pixel face.** The mockups tried Silkscreen for counters; it read poorly at the sizes we use, so it was dropped.

### Alternatives considered

- **Vendored woff2 files in `web/static/fonts/`.** No npm dependency, but binary files to keep up to date by hand. The packages give the same result with a version in the lockfile.
- **Google Fonts CDN.** Breaks the privacy test and the CSP, and tells a third party about every visit.
- **Keeping a light variant.** Doubles the design work for a theme whose character is the dark ground.

### What would change our mind

Players asking for a light mode, or an accessibility problem with the dark ground that token changes can't fix.
