# intent-harness

Intent Harness turns an ambiguous brief into explicit human choices and a reviewed handoff. It keeps assumptions and unresolved questions visible. See [docs/product/tenet.md](docs/product/tenet.md) and [docs/product/journeys.md](docs/product/journeys.md). [docs/README.md](docs/README.md) maps the rest of the documentation.

This is a local, unauthenticated proof of concept. It has two parts:

- A Python API (FastAPI) that owns the project record and every change to it.
- A React web app with two surfaces: the working brief, and review and export.

Model readings go through OpenRouter, or through canned fixture responses that make no network calls. The architecture is recorded in [docs/decisions/0001](docs/decisions/0001-python-api-and-workspace.md).

## Run it

With Docker or OrbStack installed, on a fresh checkout:

```sh
cp .env.example .env    # only if there is no .env yet; it overwrites one that exists
docker compose up --build
```

If you already have an `.env`, keep it and edit it in place. See [Upgrading an existing `.env`](#upgrading-an-existing-env).

Open http://127.0.0.1:8080. The app starts in **fixture mode**, which serves canned journey responses for the fixture texts and labels them as fixtures everywhere. Other texts are refused in this mode.

Projects persist in the `intent-data` Docker volume across restarts. `docker compose down -v` deletes them. The API is reachable only through the web container, and the web port is bound to `127.0.0.1` because there is no authentication.

### Live mode

Set these three values in `.env`, then run `docker compose up` again:

```sh
INTENT_MODEL_MODE=live
INTENT_OPENROUTER_API_KEY=...       # an OpenRouter key; it stays on the server
INTENT_MODEL=provider/model-name    # an explicit OpenRouter slug for a model with structured outputs
```

- Every model reading spends credit on your OpenRouter account.
- Startup fails if a setting is unknown, retired, invalid, or incompatible. The checks run in stages:
  1. unknown and retired names;
  2. then values;
  3. then combinations, for example live mode without a key or model.

  Each stage lists every problem it finds, but a later stage runs only after the earlier ones pass.
- Only `INTENT_*` variables are read. Shell variables such as `OPENROUTER_API_KEY`, `OPENAI_BASE_URL`, and `ANTHROPIC_*` are ignored.
- Idempotent model starts are [specified](docs/specs/idempotent-model-starts.md) but not built yet. Until then, a lost response or a resubmitted brief can start a second paid call. Implement them before regular live use.

### Upgrading an existing `.env`

An `.env` written for the earlier Express version does not start the API. Edit it in place rather than copying `.env.example` over it, which would discard your settings:

| Old line | Change |
| --- | --- |
| `ANTHROPIC_API_KEY=…` | Not read, and startup does not mention it. Live mode now goes through OpenRouter: add `INTENT_OPENROUTER_API_KEY`, and delete the Anthropic key if nothing else uses it. |
| `INTENT_EFFORT=…` | Retired, and startup names it. Rename it to `INTENT_REASONING_EFFORT`, set to `low`, `medium`, `high`, or empty. `xhigh` and `max` are not accepted. |
| `INTENT_MAX_TOKENS=…` | Retired, and startup names it. Rename it to `INTENT_MAX_OUTPUT_TOKENS`. |
| `INTENT_MODEL=<Anthropic model id>` | Must now be an OpenRouter slug, `provider/model-name`, or empty. Startup checks it even in fixture mode, but only after the retired names are fixed, and it reports only a pattern mismatch. |
| `INTENT_MODEL_MODE=…` | Unchanged: `fixture` or `live`. |

Then compare your file with `.env.example` for new optional settings.

## Develop

The toolchain versions are pinned in [`mise.toml`](mise.toml).

```sh
mise install
pnpm install
uv sync --frozen --project apps/api
pnpm dev        # API on 127.0.0.1:8000 with reload; web on http://127.0.0.1:5173 with HMR, proxying /api
```

`pnpm dev` reads `.env` the same way Compose does.

The rules and the code layout are in [AGENTS.md](AGENTS.md). The change workflow, from intake to pre-PR readiness, is in [docs/development/workflow.md](docs/development/workflow.md).

## Verify

```sh
pnpm check          # lint, format, types, tests + coverage, import boundaries, builds, contract drift, docs
pnpm e2e            # Playwright journeys with axe checks, against the real API in fixture mode
pnpm docker:smoke   # the two commands above, run on a fresh checkout, plus persistence checks
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the same scripts without any model credentials.

## How work and data behave

- **Model work is asynchronous.**
  - Submitting a brief or reply starts an operation. The page follows it through server-sent events, and you can cancel it.
  - Results apply only if the brief is unchanged since the operation started. Otherwise nothing is applied, and you are asked to reload and retry.
  - Invalid output, failures, cancellation, and timeouts all leave the last saved state as it was.
- **A paid request is never repeated blindly.**
  - A request is retried automatically only if it never reached a model: no connection could be made, or OpenRouter answered 429 or 503.
  - A request that may have reached the model is not repeated, for example after a timeout once it was sent. The operation fails and says the provider may still have charged for it. Retry sends a new request.
  - `model-calls.jsonl` records every attempt. An attempt whose outcome is unknown has its cost recorded as unknown, never as zero.
  - The reasons, with OpenRouter's documentation, are in [ADR 0001](docs/decisions/0001-python-api-and-workspace.md) under "Retries and accounting".
- **Reconnecting and restarting are safe.**
  - Reloading or reconnecting never repeats a model call.
  - After a reload, the page follows only work on the brief it shows, or work started in that same tab. Work started in another window never replaces the brief you are looking at.
  - After an API restart, unfinished operations are reported as interrupted, so they can be retried.
- **Records keep their existing format.**
  - Records are JSON files in the data directory. They are replaced atomically, and changes to one project are applied one at a time.
  - Files written by the earlier version load unchanged and render identical exports.
  - A damaged or inconsistent file is reported, with its path, instead of being skipped or replaced. An older project is never shown in its place.
  - A damaged operation record is reported the same way. Model work is paused until you check the brief and move the file out of the data directory, because the record's work may or may not have been applied.
- **One worker only.** The API must run as a single process.
- **Raw model exchanges stay local.** They are written to `model-calls.jsonl` in the data directory, which is git-ignored.

The handoff export format is described in [docs/reference/handoff-format.md](docs/reference/handoff-format.md).

## Live evaluation

`pnpm eval --budget-usd 2 --max-calls 40 --repeats 2` runs the journey variations and negative controls against the configured live model. It writes raw results and a summary to `observations/`, which is git-ignored.

The run refuses to start without a budget. It counts every request it submits, including automatic retries, and stops if any request's cost is unknown, including a request that timed out after it was sent. Judge each scenario and record the result in [docs/evaluations/live-model-observations.md](docs/evaluations/live-model-observations.md), following [the protocol](docs/evaluations/live-model-protocol.md).

## License

MIT. See [LICENSE](LICENSE).
