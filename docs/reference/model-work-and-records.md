# Model work and records

**Status:** Current · **Implemented in:** [application/operations.py](../../apps/api/src/zigzag/application/operations.py), [adapters/model/openrouter.py](../../apps/api/src/zigzag/adapters/model/openrouter.py), [adapters/persistence/files.py](../../apps/api/src/zigzag/adapters/persistence/files.py), and [features/workspace/use-workspace.ts](../../apps/web/src/features/workspace/use-workspace.ts), which are authoritative if this page disagrees.

How zigzag runs model work, handles a paid request that fails, recovers after a reload or a restart, and stores projects. Anyone running zigzag in live mode, or changing these paths, relies on it. [ADR 0001](../decisions/0001-python-api-and-workspace.md) records the decisions behind this behavior, and its known gaps.

## Model work

- Submitting a brief or a reply starts an operation. The page follows it through server-sent events, and you can cancel it.
- An operation's result applies only if the brief is unchanged since the operation started. Otherwise nothing is applied, and you are asked to reload and retry.
- Invalid output, failures, cancellation, and timeouts all leave the last saved state as it was.

## Paid requests

A paid request is never repeated blindly. ADR 0001 gives the reasons, with OpenRouter's documentation, under "Retries and accounting".

- A request is retried automatically only if it never reached a model: no connection could be made, or OpenRouter answered 429 or 503. `ZIGZAG_MAX_ATTEMPTS`, 2 by default, caps the attempts.
- A request that may have reached the model is not repeated, for example after a timeout once it was sent. The operation fails and says the provider may still have charged for it; Retry sends a new request.
- `model-calls.jsonl` records every attempt. An attempt whose outcome is unknown has its cost recorded as unknown, never as zero.
- Starting model work is not idempotent yet. A lost response, or a brief submitted again after its operation finished, starts a second paid call and creates a second project. [Idempotent model starts](../specs/idempotent-model-starts.md) specifies the fix.

## Reloads and restarts

- Reloading or reconnecting never repeats a model call.
- After a reload, the page follows only work on the brief it shows, or work started in that same tab. Work started in another window never replaces the brief you are looking at.
- After an API restart, unfinished operations are reported as interrupted, so you can retry them. A request in flight when the process stopped is not logged, and the interrupted operation does not say that it may have been charged.

## Records

- Records are JSON files in the data directory, which Compose keeps in the `zigzag_data` volume. Each file is replaced atomically, and changes to one project are applied one at a time.
- A damaged or inconsistent file is reported with its path instead of being skipped or replaced, and an older project is never shown in its place.
- A damaged operation record is reported the same way. Model work pauses until you check the brief and move the file out of the data directory, because the record's work may or may not have been applied.
- Raw model exchanges stay local, in `model-calls.jsonl` in the git-ignored data directory.

The API must run as a single process, because project locks and operation tracking live in memory. [The handoff format](handoff-format.md) describes the export.
