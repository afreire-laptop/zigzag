# zigzag

zigzag turns an ambiguous brief into explicit human choices and a reviewed handoff, keeping assumptions and unresolved questions visible. The product boundary is in [docs/product/tenet.md](docs/product/tenet.md), the expected behavior in [docs/product/journeys.md](docs/product/journeys.md), and a map of the rest of the documentation in [docs/README.md](docs/README.md).

This is a local proof of concept without authentication. A Python API (FastAPI) owns the project record and every change to it, and a React web app has two surfaces: the working brief, and review and export. Model readings go through OpenRouter, or through canned fixture responses that make no network calls; [ADR 0001](docs/decisions/0001-python-api-and-workspace.md) records the architecture.

## Run it

You need Docker or OrbStack. On a fresh checkout:

```sh
cp .env.example .env    # only if there is no .env yet: this overwrites an existing one
docker compose up --build
```

Then open http://127.0.0.1:8080. If you already have an `.env`, keep it and edit it in place, as [Upgrading](#upgrading) describes.

To use another port, set it in the shell, for example `ZIGZAG_WEB_PORT=9090 docker compose up`. Do not put `ZIGZAG_WEB_PORT` in `.env`: Compose passes `.env` to the API, which refuses settings it does not know.

The app starts in **fixture mode**: it serves canned journey responses for the fixture texts, labels them as fixtures everywhere, and refuses any other text.

Projects persist across restarts in the `zigzag_data` Docker volume, and `docker compose down -v` deletes them. Because there is no authentication, the web port is bound to `127.0.0.1`, and the API is reachable only through the web container.

### Live mode

Set these three values in `.env`, then run `docker compose up` again:

```sh
ZIGZAG_MODEL_MODE=live
ZIGZAG_OPENROUTER_API_KEY=...       # an OpenRouter key; it stays on the server
ZIGZAG_MODEL=provider/model-name    # an explicit OpenRouter slug for a model with structured outputs
```

Every model reading spends credit on your OpenRouter account. Idempotent model starts are [specified](docs/specs/idempotent-model-starts.md) but not built yet, so a lost response or a resubmitted brief can start a second paid call. Implement them before regular live use.

Only `ZIGZAG_*` variables are read; shell variables such as `OPENROUTER_API_KEY`, `OPENAI_BASE_URL`, and `ANTHROPIC_*` are ignored. Startup fails on any setting that is unknown, retired, invalid, or incompatible, and on any leftover `INTENT_*` variable. The checks run in three stages, each listing every problem it finds, and a stage runs only after the earlier ones pass:

1. names: unknown, retired, and leftover `INTENT_*` names;
2. values;
3. combinations, for example live mode without a key or a model.

## Upgrading

### From intent-harness

The project was renamed from intent-harness to zigzag. An existing checkout needs two changes:

1. In `.env`, rename every `INTENT_` variable to `ZIGZAG_`, for example `INTENT_MODEL` to `ZIGZAG_MODEL`. Startup names every leftover `INTENT_` variable with its replacement. `INTENT_EFFORT` and `INTENT_MAX_TOKENS` are retired rather than renamed; see [From the Express version](#from-the-express-version).
2. To keep the projects in the old `intent-harness_intent-data` volume, copy them into the new `zigzag_data` volume before the first start:

   ```sh
   docker compose -p intent-harness down    # stops the old stack and keeps its volume
   docker compose up --no-start --build     # creates an empty zigzag_data volume
   docker volume inspect intent-harness_intent-data >/dev/null &&
     docker run --rm --entrypoint sh -v intent-harness_intent-data:/from:ro -v zigzag_data:/to zigzag-api:local \
       -c 'if [ -n "$(ls -A /to)" ]; then echo "zigzag_data is not empty: nothing copied" >&2; exit 1; fi; cp -a /from/. /to/'
   docker compose up
   ```

   The copy stops without changing anything if the old volume does not exist, or if `zigzag_data` already holds data, for example from an earlier start. The old volume stays until you delete it with `docker volume rm intent-harness_intent-data`.

Exports now name their format `zigzag.handoff/v0`. Copies reviewed before the rename keep `intent-harness.handoff/v0`; see [the handoff format](docs/reference/handoff-format.md).

### From the Express version

An `.env` written for the earlier Express version does not start the API. Edit it in place, because copying `.env.example` over it discards your settings:

| Old line | Change |
| --- | --- |
| `ANTHROPIC_API_KEY=…` | Not read, and startup does not mention it. Live mode now goes through OpenRouter: add `ZIGZAG_OPENROUTER_API_KEY`, and delete the Anthropic key if nothing else uses it. |
| `INTENT_EFFORT=…` | Retired, and startup names it. Replace it with `ZIGZAG_REASONING_EFFORT`, set to `low`, `medium`, `high`, or empty; `xhigh` and `max` are not accepted. |
| `INTENT_MAX_TOKENS=…` | Retired, and startup names it. Replace it with `ZIGZAG_MAX_OUTPUT_TOKENS`. |
| `INTENT_MODEL=<Anthropic model id>` | Rename it to `ZIGZAG_MODEL`, set to an OpenRouter slug (`provider/model-name`) or empty. Startup checks the value even in fixture mode, but only after the names are fixed, and it reports only a pattern mismatch. |
| `INTENT_MODEL_MODE=…` | Rename it to `ZIGZAG_MODEL_MODE`. The values are unchanged: `fixture` or `live`. |

Then compare your file with `.env.example` for new optional settings.

## Develop

[`mise.toml`](mise.toml) pins the toolchain: Node, pnpm, Python, and uv.

```sh
mise install
pnpm install
uv sync --frozen --project apps/api
pnpm dev        # API on 127.0.0.1:8000 with reload; web on http://127.0.0.1:5173 with HMR, proxying /api
```

`pnpm dev` reads `.env` the same way Compose does. The rules and the code layout are in [AGENTS.md](AGENTS.md), and the change workflow, from intake to pre-PR readiness, is in [docs/development/workflow.md](docs/development/workflow.md).

## Verify

```sh
pnpm check          # lint, format, types, tests with coverage, import boundaries, builds, contract drift, docs
pnpm e2e            # Playwright journeys with axe checks, against the real API in fixture mode
pnpm docker:smoke   # "Run it" on a fresh worktree of HEAD, then stack, hardening, and persistence checks
```

`pnpm docker:smoke` tests the committed `HEAD`, so commit first; `SMOKE_E2E=1` adds the journeys against the containers. CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs the same scripts without any model credentials.

## How work and data behave

### Model work

- Submitting a brief or a reply starts an operation. The page follows it through server-sent events, and you can cancel it.
- An operation's result applies only if the brief is unchanged since the operation started. Otherwise nothing is applied, and you are asked to reload and retry.
- Invalid output, failures, cancellation, and timeouts all leave the last saved state as it was.

### Paid requests

A paid request is never repeated blindly. [ADR 0001](docs/decisions/0001-python-api-and-workspace.md) gives the reasons, with OpenRouter's documentation, under "Retries and accounting".

- A request is retried automatically only if it never reached a model: no connection could be made, or OpenRouter answered 429 or 503.
- A request that may have reached the model is not repeated, for example after a timeout once it was sent. The operation fails and says the provider may still have charged for it; Retry sends a new request.
- `model-calls.jsonl` records every attempt. An attempt whose outcome is unknown has its cost recorded as unknown, never as zero.

### Reloads and restarts

- Reloading or reconnecting never repeats a model call.
- After a reload, the page follows only work on the brief it shows, or work started in that same tab. Work started in another window never replaces the brief you are looking at.
- After an API restart, unfinished operations are reported as interrupted, so you can retry them.

### Records

- Records are JSON files in the data directory. Each file is replaced atomically, and changes to one project are applied one at a time.
- Files written by the earlier Express version load unchanged and render the same exports, except that a newly rendered export names the format `zigzag.handoff/v0`.
- A damaged or inconsistent file is reported with its path instead of being skipped or replaced, and an older project is never shown in its place.
- A damaged operation record is reported the same way. Model work pauses until you check the brief and move the file out of the data directory, because the record's work may or may not have been applied.

The API must run as a single process, because project locks and operation tracking live in memory. Raw model exchanges stay local, in `model-calls.jsonl` in the git-ignored data directory. The handoff export format is described in [docs/reference/handoff-format.md](docs/reference/handoff-format.md).

## Live evaluation

`pnpm eval --budget-usd 2 --max-calls 40 --repeats 2` runs the journey variations and negative controls against the configured live model. It writes raw results and a summary to the git-ignored `observations/`. Judge each scenario and record the result in [docs/evaluations/live-model-observations.md](docs/evaluations/live-model-observations.md), following [the protocol](docs/evaluations/live-model-protocol.md).

The run refuses to start without `--budget-usd` and `--max-calls`. It counts every request it submits, including automatic retries, and stops if any request's cost is unknown, including a request that timed out after it was sent.

It reads `.env` as `pnpm dev` does, but variables already set in the shell take precedence. To evaluate another model without editing `.env`, run `ZIGZAG_MODEL=provider/other-model pnpm eval …`. A variable left exported from an earlier session also wins over `.env`, and the summary's heading names the model it requested.

## License

MIT. See [LICENSE](LICENSE).
