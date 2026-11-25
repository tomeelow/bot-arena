# Bot Arena

A programming game: write a Python bot, upload it, and it plays other people's bots on a public ranked ladder. Every bot runs in a sandbox, every rating comes with a confidence range, and every match can be watched live or replayed.

**Status:** early development. See [the implementation plan](docs/implementation_plan.md) for progress and [the ADRs](docs/ADR.md) for the decisions behind it.

## Development

Requires [uv](https://docs.astral.sh/uv/) and Node.js 24+ (CI uses 26 LTS, from `web/.nvmrc`).

```bash
make install
```

```bash
make verify
```

`make verify` runs lint, format checks, type checks and tests for the Python packages and the web app. CI runs the same command.

| Directory | What lives there |
|---|---|
| `engine/` | The deterministic game engine. Pure Python, no dependencies; runs on CPython and Pyodide. |
| `starter_kit/` | What players install: the bot API and the `arena` CLI. |
| `sandbox/` | Running untrusted bots safely. |
| `server/` | API, match queue, workers, matchmaker, ratings. |
| `web/` | The static frontend (SvelteKit). |
| `docs/` | Plan, ADRs, game rules. |
