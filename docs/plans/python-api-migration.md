# Migration plan: Express POC to a Python API workspace

**Status:** Done locally; merged into local `main` on 2026-10-06. Some acceptance criteria remain unverified (below). · **Updated:** 2026-10-24

All stages were implemented on 2026-10-06. The Express implementation was removed from the tree after its replacement passed the gates. The [run record](../records/2026-10-06-python-api-migration.md) has the review dispositions and the accepted limitations.

The approved architecture is recorded in [decisions/0001](../decisions/0001-python-api-and-workspace.md). Each stage ends with its own checks and a local commit. Product scope stays at milestone 1, plus the focused decision-correction paths.

## Verification status

| Criterion | Status | Evidence |
| --- | --- | --- |
| `pnpm check` runs every gate locally (stage 2) | Verified locally | Passed uncached at the merged revision. |
| CI runs the same scripts (stage 2) | Unverified | The workflow file exists, but when the migration closed on 2026-10-06 the branch had never been pushed, so GitHub CI had never run. |
| Domain coverage ≥ 90%, goldens, overlapping-request tests, contract drift (stage 3) | Verified locally | Domain lines 99.4%, branches 96.6%. |
| "Test-first" (stage 3) | Not evidenced by history | Each commit contains its code and tests together, so the history cannot show the order. Existing characterization tests do not prove test-first development. |
| Deterministic failure tests for timeouts, retries, cancellation, stale results, restart, invalid output (stage 4) | Verified locally, with a stubbed transport | Real provider behavior is unverified; see [the live-model protocol](../evaluations/live-model-protocol.md). |
| Frontend coverage passes; the UI imports no backend code (stage 5) | Verified locally | |
| Playwright with axe, containers, persistence across restarts (stage 6) | Verified locally | At the last source revision: `pnpm e2e` and `SMOKE_E2E=1 pnpm docker:smoke`. |
| Live-model verification | Not run | No credentials or budget; see [the observations](../evaluations/live-model-observations.md). |

## Stages

| Stage | Work | Done when |
| --- | --- | --- |
| 1. Protect and baseline | Fix the ignore rules. Checkpoint the POC on a local branch. Record the legacy checks. Capture legacy behavior as neutral JSON: `fixtures/legacy-golden/` (records, exports, review diffs, validation outcomes) and `fixtures/journeys.json` (fixture-mode data). | The legacy `npm run check` passes, the goldens are committed, and this plan and the ADR exist. |
| 2. Workspace and gates | Set up `mise.toml`, the pnpm workspace, Turborepo, Biome, Ruff, Pyright, Vitest, pytest and coverage thresholds, import-linter, dependency-cruiser, and CI. | `pnpm check` runs every gate locally, and CI runs the same scripts. |
| 3. Domain, persistence, contracts | Port the domain to pure Python, test-first, and match the goldens byte for byte. Add the correction paths: change, own words, defer after an answer, and partial supersession. Add the file store with per-project serialization and corrupt-file recovery. Expose REST commands and the project view. Export OpenAPI and generate the client. | The domain reaches at least 90% coverage. The goldens and overlapping-request tests pass. Contract drift is checked. |
| 4. Model operations | Add the OpenRouter adapter (httpx, explicit configuration, stubbed-transport tests) and the versioned prompt. Add hedge-aware validation, the operation runner (202, SSE, REST status, cancellation, deadline, bounded concurrency, shutdown, restart recovery), and the call log. | Deterministic failure tests cover timeouts, retries, cancellation, stale results, restart, and invalid output. |
| 5. Frontend | Move the frontend to `apps/web`: generated client, shadcn/Tailwind tokens, and feature modules. Recover operations from SSE or REST. Add correction controls and focus management. | Vitest coverage passes, and the UI imports no backend code. |
| 6. Delivery | Add Playwright journeys with axe against the real services in fixture mode. Add containers, Compose, and the persistence check. Add the evaluation runner. Update the docs. Remove the legacy implementation. | Every deterministic gate is green, `docker compose up --build` serves the fixture app, data survives a container restart, and the legacy code is gone. |

## Risks carried into implementation

- Live-model evidence needs credentials and a budget. Without them, the live path is built and tested against stubs, and live verification is marked *not run*.
- Provider schema enforcement varies. Validation in the API is the guarantee, and a model with a high rejection rate is a finding, not a bug to hide.
- The API runs as a single process only. Locks and operation tracking live in memory, and do not extend across workers.
