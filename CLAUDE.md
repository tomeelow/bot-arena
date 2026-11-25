# CLAUDE.md

Guidance for Claude when working in this repository.

## Project context

**Bot Arena** is a programming game. People write Python bots, upload them, and the bots play each other on a public ranked ladder. The platform runs every bot in a sandbox, rates it with an honest confidence range, and lets anyone watch matches live or as replays. A self-play RL bot sits at the top of the ladder as the "boss" to beat.

The game is an original 1v1, simultaneous-move strategy game on a grid with fog of war and limited resources. The engine is deterministic and seeded. Practice matches run in the user's browser (Pyodide). Only ranked matches use the server.

The point of this project is the **platform**, not the game AI: deterministic engine → sandboxed bot execution → match queue → ratings with uncertainty → replays and live spectating → real users. The RL boss is one bot on the ladder, held to the same rules as everyone else.

Three things set this project apart, and none of them may be quietly dropped:

1. **Bot code is hostile.** Every bot is untrusted code from a stranger. The platform survives any bot: crashes, hangs, memory bombs, escape attempts. A bot that misbehaves loses its match, and nothing else is affected.
2. **Determinism.** The same seed and the same orders give the same match, bit for bit, on CPython and in Pyodide. Replays, debugging, fair comparisons and rating audits all depend on this.
3. **Honest uncertainty.** Every rating comes with a confidence range. The site says how sure it is ("A is stronger than B with 87% confidence"), never just a number.

There is also one hard constraint: **it costs nothing to run.** One free-tier server, static hosting for the frontend, practice in the browser. A feature that needs paid infrastructure gets redesigned or cut. It never gets quietly billed.

The phased plan, with status and exit criteria, is in `docs/implementation_plan.md`. Decisions are recorded in `docs/ADR.md`. The game rules are in `docs/GAME_RULES.md`.

## Core principles

- **Concise over clever.** Smallest amount of code that solves the problem clearly.
- **No premature abstraction.** Don't add layers, factories, or config switches until a second concrete use case exists.
- **Best practices, not ceremony.** Follow Python idioms; don't import patterns from other ecosystems just because they're familiar.
- **Readable beats compact.** Concise is not the same as obfuscated.
- **Delete more than you add.** When refactoring, the diff should usually shrink.

## Working with the plan

- `docs/implementation_plan.md` is the source of truth for what is done and what comes next. Read its progress tracker before starting work.
- Work in the current phase. Don't build a later phase's infrastructure early just because you're nearby.
- When a deliverable lands, tick its exit criterion and update the phase status **in the same branch**. Tick a box only once the criterion has been verified, not when the code is written.
- If code would contradict an ADR, stop and ask. Don't drift away from it silently. New decisions get a new ADR entry that lists the alternatives and what would make us change our mind.

## Git workflow

- **Branch per change.** Never commit features or fixes directly to `main`. Use `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- **One concern per branch.** If scope grows, split.
- **Commit messages: short, imperative, descriptive. No filler.**
  - Good: `feat: add fog-of-war observation builder with leak test`
  - Good: `fix: resolve move swaps symmetrically regardless of seat`
  - Good: `chore: pin pyodide and align engine Python version`
  - Bad: `updates`, `WIP`, `various changes`, `fixed stuff`
- **Squash noisy histories before merging.** Keep `main` linear and readable.
- **Never commit secrets.** The GitHub OAuth client secret, the session signing key and storage credentials live in the environment; provide `.env.example` instead.
- **Never commit user data, replays, databases or model weights.** Boss weights ship as a release asset next to their model card.

## Code quality

- **`make verify` is the single entry point:** lint, format check, typecheck and tests for both Python and the frontend. Run it before calling anything done, and say what it showed.
- **Python:** type hints on public functions; `ruff` for lint, `ruff format` for formatting; `pyright` for type checking; `pytest` and `hypothesis` for tests.
- **TypeScript (frontend):** strict mode; `tsc --noEmit` is part of `make verify`.
- **Dependencies:** pin them. Python uses a `uv` workspace; the frontend uses npm with a committed lockfile. The engine has **zero** runtime dependencies so it loads instantly in Pyodide and in the sandbox.
- **Python version:** the engine and starter kit target the Python version that ships with the pinned Pyodide release. Bumping Pyodide is a deliberate change of its own.
- **Configuration:** environment variables for secrets; TOML in `config/` for limits, ladder parameters, matchmaker weights and caps. No hardcoded limits, paths, endpoints or magic numbers.
- **Logging over print** in platform code. Log match ids, bot version ids, end reasons and durations. Never log bot source code or full observations.
- **Rules become checks.** Engine purity is enforced by ruff's banned-API list and import-linter contracts, not by remembering. If a rule here can become a lint rule, type or test, make it one.
- **Tests where it matters.** Required for game rules, determinism, fog of war, the sandbox (adversarial suite), ratings math, the replay round-trip and matchmaker invariants. Not required for throwaway spikes.
- **Spikes and notebooks are scratch space.** If the logic matures, move it into a package. Never import from them.

## Arena-specific practices

### The sandbox rule (most important rule in this repo)

Everything that comes from a bot is hostile: its code, its output, its timing and its logs.

- Bot code is only ever imported, executed or even compiled **inside the jail**. On the host it is bytes that get stored and hashed, nothing more.
- Each bot gets **its own fresh jail for each match**: no network, a read-only filesystem plus a small tmpfs, an empty environment (no secrets), memory, CPU and process limits, and a non-root user. It is destroyed when the match ends. Jails are never reused across matches.
- Everything that crosses the boundary is untrusted input. Parse it on the host with a strict schema, size limits and a turn-number check. The harness runs inside the jail, so it is untrusted too.
- **The host measures time; the bot never reports it.** Per-turn CPU time comes from host-side accounting, with a time bank, plus a wall-clock backstop, because a sleeping bot uses no CPU.
- **Import allowlists are a UX feature, not a security boundary.** The jail is the boundary.
- **Pyodide is not a sandbox on its own.** `import js` reaches the host JS runtime. On the server, Pyodide runs under a runtime with every permission denied except reading its own distribution, inside the OS jail.
- Any change to the jail, the harness, the protocol or the limits has to pass the adversarial suite (`sandbox/adversarial/`). A new escape idea gets a new adversarial bot first, then the fix.

### Determinism

- **The engine is pure.** No I/O, no clock, no environment reads, no global state, no threads. Lint and import contracts enforce this.
- **One RNG.** A `random.Random(seed)` instance passed explicitly. Never the module-level `random` functions.
- **Integer arithmetic only** in game rules. No floats in game state.
- **No hash-order dependence.** Never iterate a `set` (or anything ordered by `hash()` of a str) in rule logic. Sort it or keep insertion order. `PYTHONHASHSEED` must not be able to change a match.
- **Seat order never matters.** Simultaneous resolution never depends on the seat index. A contested outcome gets a symmetric rule (split it, or nobody gets it), never "player 0 first".
- **Replays store orders, not bot code.** Seed + config + per-turn orders is the canonical replay. Viewer frames are derived from it by the engine.
- **Every replay is re-simulated before its result is rated.** A hash mismatch voids the match and is treated as a bug.
- Golden replays run in CI on both CPython and Pyodide and must produce identical hashes.

### The observation rule (fog of war)

A bot's observation is the game state filtered by that player's visibility, and nothing else.

- Two states that differ only in what player P cannot see must produce **byte-identical** observations for P. A hypothesis property test enforces this.
- **No side channels.** Enemy units carry no ids, and nothing exposes global counters, enemy resource totals, the opponent's invalid orders or the opponent's identity.
- **Observations are seat-relative.** Each bot sees the map from its own seat, so both seats are exactly equivalent and a seat-swap test can prove it.
- Any new observation field ships with a fog test for that field.

### One engine, one protocol, one viewer

- **One engine everywhere:** the local runner, browser practice, ranked workers and RL training all use the same Python package. Never reimplement rules in TypeScript or anywhere else. The one allowed exception is a batched engine used only for RL training, and only if differential tests on recorded replays show it matches the reference engine.
- **One bot protocol and one harness** for local, browser and ranked play. They differ only in isolation and how limits are enforced.
- **One viewer.** A live match is a replay that is still being written. Both use the same frame format and the same component.
- **The engine version covers rules, observation schema, order schema and replay format together.** Every replay and every rating records it. An incompatible change bumps it and starts a new ladder season.

### Ratings and evaluation

- **Results are the source of truth; ratings are derived.** Rebuilding ratings from the results log must reproduce the stored ratings exactly.
- **Never rate a match the platform broke.** Platform errors void the match. Only failures caused by the bot (timeout, crash, memory, invalid output) count as losses.
- **Rank by a conservative estimate** (μ − kσ), show the interval, and mark bots as provisional until σ falls below the threshold. Never rank by μ alone.
- **"Stronger than" is not "wins the next match".** P(skill A > skill B) and P(A beats B in one game) are different numbers. Label which one is shown.
- **Validate the rating system on synthetic ladders** with a known true order before users rely on it: ordering recovery, calibration, and games needed to converge. Set the targets before the run. If a target is missed, report it and fix the system; don't move the target.
- **Version comparisons use paired seeds.** Each seed is played from both seats, and the result is reported with a confidence interval, never as a raw win count.
- **RL boss:** never report self-play Elo on its own. Report results against fixed scripted baselines, with confidence intervals. The boss goes through the normal upload pipeline with the same sandbox, limits, observations and size cap as everyone else. No backdoor.

### Ladder integrity and user safety

- Bots from the same owner never play rated matches against each other.
- Cap active bots per user. Rate-limit uploads, comparison runs and live viewers.
- **Bot logs are visible only to the bot's owner.** Public replays show moves, not debug output.
- **Bot names, descriptions and logs render as text, never as HTML.** The frontend ships a strict CSP.
- **User bot code is private.** It is never served to other users and never shipped to other people's browsers. The browser only runs the user's own code and our built-in bots.

### Zero cost

- Before adding any service, confirm it is free at the usage we expect, and record its terms and the date you checked them in the ADR. Free tiers change: Hugging Face Spaces stopped being free partway through an earlier project.
- **Every unbounded resource gets a cap in config:** matches per day, replay and log retention, log bytes per match, uploads per user, concurrent spectators.
- **SQLite is the database and the queue.** No Redis, Postgres or Celery until the single-server design measurably fails.
- RL training runs offline on a dev machine or free notebook compute, never on the production server.

### Users and metrics

- Usage metrics come from our own database and server events, in aggregate. No third-party trackers or analytics scripts.
- Collect the minimum: a GitHub id and handle for login. Nothing else without asking.

## Ask before acting

When unsure, stop and ask. In particular, ask before:

- Changing the game rules after the v1 freeze, or the observation, order or replay schemas (these bump the engine version and can reset the ladder)
- Anything that touches the sandbox boundary: jail config, limits, allowed modules, the harness protocol
- Changing the rating system, the ranking formula or the matchmaker's fairness rules, or anything that rewrites stored ratings or results
- Anything that deletes or rewrites stored matches, replays, user bots or user data
- Anything that could expose user bot code or private logs
- New external services or dependencies, especially any that could cost money
- Running anything that changes data on the production server
- Publishing, posting or announcing anything publicly
- Anything that rewrites git history on shared branches
