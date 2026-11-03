# Contributing to zigzag

This file is for people who change zigzag or run it with real data or an OpenRouter key. [The README](README.md) covers what zigzag is and how to start it.

## Set up

[`mise.toml`](mise.toml) pins the toolchain: Node, pnpm, Python, and uv.

```sh
mise install
pnpm install
uv sync --frozen --project apps/api
pnpm dev        # API on 127.0.0.1:8000 with reload; web on http://127.0.0.1:5173 with HMR, proxying /api
```

`pnpm dev` reads `.env` the same way Compose does. The README's `cp .env.example .env` overwrites an existing `.env`, so if you already have one, keep it and edit it in place.

[AGENTS.md](AGENTS.md) holds the rules and the code layout. [The development workflow](docs/development/workflow.md) takes a change from intake to pre-PR readiness, and [docs/README.md](docs/README.md) says which document a change needs.

## Before you run it

### Data and security

- zigzag runs locally, for one user, without authentication. Compose therefore binds the web port to `127.0.0.1`, and the API is reachable only through the web container.
- Projects persist across restarts in the `zigzag_data` Docker volume, and `docker compose down -v` deletes them.
- The OpenRouter key stays on the server and is never sent to the browser.

### Cost

- Every model reading in live mode spends credit on your OpenRouter account.
- `ZIGZAG_MODEL` must name a model that supports structured outputs.
- Starting model work is not idempotent yet, so a lost response or a resubmitted brief can start a second paid call. The fix is [specified](docs/specs/idempotent-model-starts.md) and scheduled before regular live use.

### Configuration

[`.env.example`](.env.example) describes each model and limit setting, with its default. Only `ZIGZAG_*` variables are read; shell variables such as `OPENROUTER_API_KEY`, `OPENAI_BASE_URL`, and `ANTHROPIC_*` are ignored.

Startup fails on any setting that is unknown, invalid, or incompatible. The checks run in three stages, each listing every problem it finds, and a stage runs only after the earlier ones pass:

1. names;
2. values;
3. combinations, for example live mode without a key or a model.

## Checks

```sh
pnpm check          # lint, format, types, tests with coverage, import boundaries, builds, contract drift, docs
pnpm e2e            # Playwright journeys with axe checks, against the real API in fixture mode
pnpm docker:smoke   # the README's "Run it" on a fresh worktree of HEAD, then stack, hardening, and persistence checks
```

Run `pnpm check` before you open a pull request. `pnpm docker:smoke` tests the committed `HEAD`, so commit first; `SMOKE_E2E=1` adds the journeys against the containers. CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the same scripts without any model credentials.

## Live evaluation

`pnpm eval` runs the journey variations and negative controls against the configured live model. It spends money, refuses to start without a budget, and never runs in CI. [The live-model protocol](docs/evaluations/live-model-protocol.md) says how to run, judge, and record an evaluation.
