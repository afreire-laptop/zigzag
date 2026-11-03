# Idempotent model starts

**Status:** Ready for implementation; not started · **Updated:** 2026-11-03 · **Scheduled:** before regular live-model use (owner's instruction, 2026-10-06) · **Origin:** Codex pass 7 in the [migration run record](../records/2026-10-06-python-api-migration.md), recorded as a known gap in [ADR 0001](../decisions/0001-python-api-and-workspace.md)

## Problem

Three routes start paid model work:

- `POST /api/projects`
- `POST /api/projects/{id}/replies`
- `POST /api/projects/{id}/assessments`

Each request creates a new operation, and `OperationRunner._spawn` in `apps/api/src/zigzag/application/operations.py` refuses a duplicate only while the first operation is active in memory. As a result:

- If a create's `202` is lost, or the brief is resubmitted after its operation ends, the API starts another paid call and creates a second project.
- Replies and reassessments carry a base revision, which protects some retries. A reassessment that added nothing leaves the revision unchanged, so repeating it pays for another call.
- The web client's resume-after-reload and same-request `busy` matching cover only the running operation. They cannot replay a finished start.

Running on localhost reduces the exposure, but it does not prevent lost responses, reloads, or retries.

## Scope

This is application replay protection: one logical user action starts at most one operation, and asking again returns that operation.

It does not promise:

- Exactly-once execution or billing at the provider. OpenRouter documents no idempotency key for chat completions. A process crash after dispatch, or an ambiguous transport failure, can still leave a charge whose outcome is unknown. ADR 0001 keeps its existing rule that such a request is never repeated automatically.
- Deduplication across processes. The API stays single-process.
- Treating two separate user actions with identical text as one. A deliberate new action gets a new key.

The evaluation runner calls the assessor directly, without the operation runner, so it is unaffected.

## Design

1. Each start request carries an `Idempotency-Key` header: an opaque client-generated token matching `^[A-Za-z0-9_-]{16,128}$`, with one key per logical action. A missing or malformed key is rejected with `400` and the `invalid-idempotency-key` problem type, before any other work.
2. The API derives a request fingerprint from the operation kind, project id, base revision, question id, and trimmed text. The key identifies the action, and the fingerprint detects reuse of a key for a different request.
3. The key and fingerprint are registered durably before dispatch, as new fields of `OperationRecord`. They are written in the record's first save, which already happens before the task is created, so a failed save means that no task and no model call exist. Both fields are optional, so existing operation records still load, and a record without a key never matches.
4. Every `start_*` method looks up the key before any other check except the damaged-record pause. The checks it precedes are the base-revision check, `busy`, and project lookup. The lookup has three outcomes:
   - The key is known and the fingerprint matches: the API returns the original operation in its current state, terminal or not, with the same `202` and `Location`, plus `Idempotent-Replayed: true`. It starts no model call.
   - The key is known and the fingerprint differs: the API rejects the request with `422` and the `idempotency-key-reused` problem type. Nothing changes.
   - The key is unknown: the existing checks and registration run.
5. The check and the registration are atomic. The in-memory index from key to operation id is updated in the same synchronous step that saves the record, with no `await` between the lookup and the registration, so one event loop admits only one registration per key.
6. At startup, the index is rebuilt from the operation records. A replayed key whose operation was interrupted returns that `interrupted` operation.
7. While any operation record is unreadable, model starts stay paused by the existing `corrupt-record` problem, so an unreadable record is never mistaken for an unknown key.
8. The web client generates a key when the user acts: submitting a brief, sending a reply, or requesting a reassessment. It reuses that key only to resend the same action, for example after a network error with no response. A Retry after a failure, and a deliberate resubmission, are new actions with new keys. The key is generated in `platform/` and passed through the generated client; no domain rule moves to TypeScript.
9. The header is declared on the three routes in the Pydantic and FastAPI layer, and `pnpm contract` regenerates the contract.

## Acceptance criteria

Each criterion is an observable test at the highest useful seam: the application runner with fakes, or the HTTP harness in `apps/api/tests/api/`.

1. **One key per logical action.** A start without a valid key gets `400` and creates no operation, no record, and no model call.
2. **Durable registration before dispatch.** The record holding the key and fingerprint is saved before the assessor is called. If that save raises, there is no task and no model call.
3. **Replay after completion.** The same key and payload, after the operation succeeded, return the same operation id with status `succeeded`. The assessor call count and the project count are unchanged.
4. **Replay after restart.** A new runner over the same data directory returns the original operation for the key. An operation interrupted by the restart is returned as `interrupted`, without a new call.
5. **Lost response.** A create is started and its response discarded, then the same request is sent again with the same key. The result is one operation, one model call, and one project.
6. **Simultaneous requests.** Two concurrent requests with one key start exactly one operation and one model call. Both responses name that operation.
7. **Conflicting payload.** One key with a different text, kind, project, base revision, or question gets `422 idempotency-key-reused`. The original operation is unaffected, and no model call starts.
8. **A new action uses a new key.** The same payload with a new key after completion starts a new operation, and for a create, a new project. A web client test shows that Retry and resubmission send new keys, and that resending after a network error reuses the key.
9. **Reply and reassessment replay.** Replaying a finished reply or reassessment returns the original operation, not a base-revision conflict. This covers the reassessment that left the revision unchanged.
10. **Terminal-result replay.** For each terminal status (`succeeded`, `failed`, `cancelled`, and `interrupted`), a replay returns that operation unchanged and starts nothing.
11. **Damaged records.** With an unreadable operation record present, a start with any key returns `corrupt-record`. No key is treated as unknown.

## Verification

- Write the tests first, and confirm that each one fails against the current runner for the stated reason.
- Run `pnpm contract`, then `pnpm check`. Because the routes and the web client change, also run `pnpm e2e` and `SMOKE_E2E=1 pnpm docker:smoke`.
- Update ADR 0001: replace the known gap with the decision, and keep the limits above. Update [model work and records](../reference/model-work-and-records.md), and the live-mode warning in the README.
- Get independent Claude and Codex reviews, per [the development workflow](../development/workflow.md).

## Likely affected files

`apps/api/src/zigzag/application/operations.py`, `adapters/http/app.py`, `adapters/http/schemas.py`, `adapters/persistence/files.py` (record format), `apps/api/tests/application/test_operations.py`, `apps/api/tests/api/`, `apps/web/src/platform/api.ts`, `apps/web/src/features/workspace/use-workspace.ts`, and the generated contract.
