# ADR 0001: Python API, pnpm/Turborepo workspace, and asynchronous model operations

**Status:** Accepted, 2026-10-06. **Supersedes:** the single Express process described in the POC README.

## Context

The milestone 1 POC ran as one Express process with a React client and a shared Zod domain. A read-only audit (2026-10-06) found the domain sound. It also found these gaps:

- Decisions could not be fully revised. A deferral recorded inside a reply stayed displayed as current after the question was answered.
- Model calls had no deadline, configuration failed open, and provider credentials were inherited implicitly.
- The UI imported domain functions directly.
- There was no CI, container, or live evidence.

The owner has approved a migration to a Python API and a separately built web application, with OpenRouter as the model gateway. This ADR records that decision and the constraints the implementation keeps.

## Decision

**Repository.** One pnpm workspace orchestrated by Turborepo, containing:

- `apps/api`: a Python FastAPI service. uv manages its dependencies; the package scripts are thin wrappers around `uv run`.
- `apps/web`: React, Vite, and strict TypeScript. Components use shadcn/ui and Tailwind. CSS Modules are allowed only where isolated custom styling is justified.
- `packages/api-client`: TypeScript types, an SDK, and Zod validators, all generated from the API's OpenAPI document.

Turborepo runs Python tasks through those package scripts. This is the documented, stable way to run non-JavaScript workspaces; no experimental Turborepo–uv integration is used. Tool versions are pinned in `mise.toml`, the package manifests, `uv.lock`, and `pnpm-lock.yaml`.

**Authority.** The API owns durable state and every domain transition. The browser holds only draft interaction state, never model credentials, and imports only the generated client. The API returns a *project view* that already carries the derived facts the UI needs, so the UI never re-implements domain rules. These include the basis for each statement, the currency of each decision, and which actions each question permits.

**Contracts.** Pydantic models are authoritative for transport, and the exported `openapi.json` is the contract artifact. FastAPI's native SSE support places event payload schemas in that document. The client generator turns them into types and runtime validators. CI regenerates both artifacts and fails on drift.

**API layering.**

- `domain`: pure, immutable, frozen models with tuple collections and explicit typed outcomes.
- `application`: use cases, ports, and the operation runner.
- `adapters`: HTTP, file persistence, the OpenRouter client, and the fixture assessor.
- One composition root.

import-linter enforces the layering. dependency-cruiser enforces the web feature boundaries.

**Persistence.**

- Each project stays a JSON file, in the record format the POC already used (`schemaVersion: 1`). Existing records and reviewed exports load and render unchanged. Golden files captured from the legacy implementation check this.
- Writes use atomic replacement. The whole check-revision, read, modify, save sequence is serialized per project with an in-process lock.
- A save raises only if the stored record is unchanged, so every caller can treat a raised save as nothing written. Everything that can fail runs before the rename: opening the directory, and writing and syncing the temporary file. A failed write removes its temporary file.
- The directory sync that makes the rename durable can only run after the rename. If that sync fails, the new record is already what every reader sees, so the save does not raise. The failure is logged, because on a disk that reports errors the rename may not survive a crash. This risk is accepted for a single-user local tool: such a disk needs attention anyway, and failing the request would wrongly report a visible change as not made.
- A corrupt or inconsistent file is never modified or skipped silently. The API reports it as a recovery state.
- An operation file that cannot be read is also never modified or skipped. Whether its work reached the project is unknown, so a retry could repeat that work. The API therefore refuses new model work with a `corrupt-record` problem that names the file, and lists the file in `GET /api/status`, which the interface shows. Model work resumes once the file is moved out of the data directory. Decisions and edits remain available, because they never repeat model work.
- **Deployment constraint:** the API runs as a single process with one worker. It is not safe to run multiple workers.

**Model operations.**

- Every model assessment is an asynchronous operation. The API returns `202` with an operation id and a status location. A per-operation SSE stream sends progress and terminal notifications.
- The operation record is persisted, and REST status is authoritative. SSE only signals that persisted state changed, so reconnecting never repeats a paid call.
- The runner:
  - bounds concurrency with a semaphore and allows one active operation per project;
  - applies a total deadline that includes retries;
  - supports cancellation and tracks every task;
  - drains tasks on shutdown.
- Results are applied only if the project is still at the operation's base revision. The terminal notification is sent only after the project and the operation are durably saved.
- After a restart, an unfinished operation becomes `interrupted`, unless its commit marker shows that the project write completed. The marker is written in the same atomic save as the operation's notes and model call. A recovered success is therefore reported exactly as it would have finished, including every attempt and its cost status.
- The same check settles an operation that ends with an unexpected error. For example, the project may have been saved when recording the operation's success fails. If the project matches the marker, the operation succeeded. If the project cannot be read to confirm it, the operation is reported as unconfirmed rather than unchanged, and the interface does not offer a retry, because a retry could apply the change twice.
- **Known gap: starting model work is not idempotent.** Recorded 2026-10-06 from an adversarial review; not fixed.
  - Requests that start model work carry no client idempotency key. The runner refuses a duplicate only while the first operation is still active in memory, and creates share one slot.
  - If a create's `202` response is lost, or the same brief is submitted again after its operation finished, the API starts a new, separately paid model call and creates a second project.
  - Replies and reassessments carry a base revision. Once a result has changed the brief, an identical retry is refused as a conflict before any model call. A reassessment that added nothing leaves the revision unchanged, so repeating it pays for another call, but it cannot change the brief twice.
  - The web client narrows the gap only while the first operation is active: after a reload it resumes its own operation, and on a `busy` response it follows the running operation if that is the same request.
  - Accepted for now: the API is local, single-user, and reached on loopback, where a lost `202` is rare. A user deliberately resubmitting a finished brief may also mean to start again.
  - Remedy: a client-generated idempotency key on each start command, persisted with the operation, so a resubmitted key returns the original operation, including a finished one, across restarts. Specified in [idempotent model starts](../specs/idempotent-model-starts.md) and scheduled before regular live-model use. Not yet implemented; the gap stands until then.

**Model gateway.** OpenRouter's OpenAI-compatible Chat Completions endpoint, with:

- `response_format: json_schema` in strict mode;
- `provider.require_parameters: true`, so requests are routed only to endpoints that honour the schema;
- an explicit model slug.

It is the endpoint OpenRouter documents for structured outputs across model families. The adapter is a single module built on httpx that takes all of its configuration explicitly. It never reads `OPENAI_*`, `ANTHROPIC_*`, or base-URL variables from the shell.

The provider schema is derived from the Pydantic proposal model. Keywords that providers do not consistently enforce are removed from it. Full validation, including lengths, counts, quote matching, references, and hedge detection, always runs in the API before any mutation.

**Retries and accounting.** Added 2026-10-06, after an adversarial review found that a timed-out request could be paid for twice. A request is repeated automatically only when no model can have processed it. OpenRouter sends `200 OK` "as soon as the provider accepts the request", and reports every failure after that point inside the response body ([Errors and debugging](https://openrouter.ai/docs/api_reference/errors-and-debugging), "Mid-stream errors"). An error status therefore means that no provider accepted the request.

- **Repeated automatically**, up to `ZIGZAG_MAX_ATTEMPTS` attempts in total:
  - failures before the request was sent: `ConnectError`, `ConnectTimeout`, and `PoolTimeout`;
  - `429`, from an OpenRouter platform limit or a provider's rate limit. The docs say to retry with backoff and to honour `Retry-After` ([Limits](https://openrouter.ai/docs/api_reference/limits), "Handling 429 errors");
  - `503`, "There is no available model provider that meets your routing requirements" (errors page).

  A `Retry-After` longer than the client's 8-second backoff cap is not shortened. The failure goes to the user instead.
- **Never repeated automatically, because the request may have been processed and charged.** This covers:
  - read and write timeouts, read and write errors, and dropped connections;
  - `408` ("Your request timed out");
  - `502` ("we received an invalid response from" the model);
  - `504` (the provider "did not respond within the allowed time"), and any other 5xx;
  - an unreadable `200`, a `200` with no choices or with only an `error` object, and `finish_reason: "error"`.

  These fail the operation as retryable. The user's Retry starts a new operation and sends a new, separately paid request.
- **Never retryable:** other 4xx statuses, which are rejections before processing.
- **No idempotency key.** The chat completion API reference documents no idempotency or deduplication header. The only idempotency key in OpenRouter's docs belongs to the unrelated Interns API. A repeated request therefore cannot be deduplicated, and the client does not invent a key.
- **Charges on failed responses stay unknown.** The docs disagree about them:
  - [Zero Completion Insurance](https://openrouter.ai/docs/guides/features/zero-completion-insurance) says that a response with an error finish reason is not billed for model tokens.
  - The errors page says that "you may still be charged for the prompt processing cost by the upstream provider, even if no content is generated".
  - Neither covers a response the client never read.
- **Every attempt is accounted for.**
  - The assessor appends a `CallAttempt` (`answered`, `not-processed`, or `ambiguous`) to a list that the caller owns, as each request settles. This includes a request cut off by the deadline, a cancel, or a shutdown, so the record survives a call that never returns.
  - `model-calls.jsonl` has one line per attempt. An ambiguous attempt's cost is `unknown-may-have-been-charged`, never zero, and a not-processed attempt's is `not-charged`.
  - The operation's `modelCall` reports `attempts`, `ambiguousAttempts`, and a cost that is unknown whenever any attempt's cost is unknown.
  - When a deadline, cancel, or shutdown cuts off a request, the error says that nothing in the brief changed, but that the provider may still have processed and charged for the request.
  - The evaluation budget counts every attempt and stops at the first unknown cost.
- **Known gap:** attempts are logged when they settle. If the process dies while a request is in flight, the request is not logged, and restart recovery reports the operation as interrupted without saying that it may have been charged.

**Delivery.**

- Each runtime service runs in a Docker container: the API on Python slim, the web app on unprivileged nginx.
- Docker Compose orchestrates them. The API is reachable only on the Compose network, and the web entry point binds to `127.0.0.1`.
- CI runs the same package scripts used locally and needs no model credentials.

## Version choices with a reason

The versions themselves live in the manifests and lockfiles.

- **TypeScript stays on the 6.0 line, not 7.0.** TypeScript 7.0 does not ship the classic compiler API. The client generator calls that API and crashes under 7.0 (`ts.SyntaxKind` is undefined), which was reproduced on 2026-10-06. Revisit this when the generator supports TypeScript 7.
- **Node 24 (Active LTS).** Node 26 does not become LTS until 2026-10-28.
- **Python 3.14**, the newest release with full wheel coverage for the dependencies.

## Consequences

- The domain exists only in Python. The UI's only knowledge of it is the generated contract and the project view.
- Running two languages costs some setup. A fresh machine needs only Docker for the fixture application. Local development needs the tools pinned in `mise.toml`.
- The legacy Express implementation stays available only until the replacement passes the deterministic gates, and is then removed from the runtime and the tree.

## Not adopted

- A Node backend-for-frontend, Next.js, or Fastify.
- Redis, Kafka, a generic event bus, or event sourcing.
- A database.
- Automatic model routing or classifiers.
- Multi-agent orchestration.
- The later changing-brief milestone.
