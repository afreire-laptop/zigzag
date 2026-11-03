# zigzag

zigzag is a proof of concept that turns an ambiguous brief into explicit human choices and a reviewed handoff. Assumptions and unresolved questions stay visible, and the model only proposes: intent changes only through the user's own choices and instructions.

[The product tenet](docs/product/tenet.md) sets the product boundary, and [the journeys](docs/product/journeys.md) fix the expected behavior. [docs/README.md](docs/README.md) maps the rest of the documentation.

It runs locally, for one user, without authentication.

## Stack

- A Python API in FastAPI and Pydantic, managed by uv. It owns the project record and every change to it.
- A React web app, built with Vite, with two surfaces: the working brief, and review and export. It reaches the API only through a client generated from the API's OpenAPI document.
- Model readings from OpenRouter in live mode, or from preset fixture responses that make no network calls.
- Docker Compose to run the app, and a pnpm and Turborepo workspace to develop it.

[ADR 0001](docs/decisions/0001-python-api-and-workspace.md) records the architecture and the reasons for it.

## Run it

You need Docker or OrbStack. On a fresh checkout:

```sh
cp .env.example .env    # only if there is no .env yet: this overwrites an existing one
docker compose up --build
```

Then open http://127.0.0.1:8080. If you already have an `.env`, keep it and edit it in place; [Upgrading](#upgrading) covers one from an earlier version.

The app starts in **fixture mode** by default: it serves preset journey responses for the fixture texts, labels them as fixtures everywhere, and refuses any other text.

To use another port, set it in the shell, for example `ZIGZAG_WEB_PORT=9090 docker compose up`. Do not put `ZIGZAG_WEB_PORT` in `.env`: Compose passes `.env` to the API, which refuses settings it does not know.

Projects persist across restarts in the `zigzag_data` Docker volume, and `docker compose down -v` deletes them. Because there is no authentication, the web port is bound to `127.0.0.1`, and the API is reachable only through the web container.

### Live mode

Set these three values in `.env`, then run `docker compose up` again:

```sh
ZIGZAG_MODEL_MODE=live
ZIGZAG_OPENROUTER_API_KEY=...       # an OpenRouter key; it stays on the server
ZIGZAG_MODEL=provider/model-name    # an explicit OpenRouter slug for a model with structured outputs
```

Every model reading spends credit on your OpenRouter account. Starting model work is not idempotent yet, so a lost response or a resubmitted brief can start a second paid call. The fix is [specified](docs/specs/idempotent-model-starts.md) and scheduled before regular live use.

### Configuration

[`.env.example`](.env.example) describes each model and limit setting, with its default. Only `ZIGZAG_*` variables are read; shell variables such as `OPENROUTER_API_KEY`, `OPENAI_BASE_URL`, and `ANTHROPIC_*` are ignored.

Startup fails on any setting that is unknown, retired, invalid, or incompatible, and on any leftover `INTENT_*` variable. The checks run in three stages, each listing every problem it finds, and a stage runs only after the earlier ones pass:

1. names: unknown, retired, and leftover `INTENT_*` names;
2. values;
3. combinations, for example live mode without a key or a model.

## Upgrading

An `.env` written for intent-harness, this project's former name, or for the earlier Express version stops startup. Edit it in place, because copying `.env.example` over it discards your settings. [The upgrade guide](docs/development/upgrading.md) lists each setting to change, and gives the commands that copy your projects out of the old `intent-harness_intent-data` volume.

## Contributing

[`mise.toml`](mise.toml) pins the toolchain: Node, pnpm, Python, and uv.

```sh
mise install
pnpm install
uv sync --frozen --project apps/api
pnpm dev        # API on 127.0.0.1:8000 with reload; web on http://127.0.0.1:5173 with HMR, proxying /api
```

`pnpm dev` reads `.env` the same way Compose does. [AGENTS.md](AGENTS.md) holds the rules and the code layout, and [the development workflow](docs/development/workflow.md) takes a change from intake to pre-PR readiness.

### Checks

```sh
pnpm check          # lint, format, types, tests with coverage, import boundaries, builds, contract drift, docs
pnpm e2e            # Playwright journeys with axe checks, against the real API in fixture mode
pnpm docker:smoke   # "Run it" on a fresh worktree of HEAD, then stack, hardening, and persistence checks
```

`pnpm docker:smoke` tests the committed `HEAD`, so commit first; `SMOKE_E2E=1` adds the journeys against the containers. CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the same scripts without any model credentials.

### Live evaluation

`pnpm eval` runs the journey variations and negative controls against the configured live model. It spends money, refuses to start without a budget, and never runs in CI. [The live-model protocol](docs/evaluations/live-model-protocol.md) says how to run, judge, and record an evaluation.

## How it behaves

A model result applies only if the brief is unchanged since the work started, and a request that may have reached the model is never repeated automatically. [Model work and records](docs/reference/model-work-and-records.md) covers operations, paid requests, reloads and restarts, and how projects are stored. [The handoff format](docs/reference/handoff-format.md) describes the export.

## License

MIT. See [LICENSE](LICENSE).
