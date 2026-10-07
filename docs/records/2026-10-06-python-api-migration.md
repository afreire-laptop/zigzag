# Python API migration: run record

**Status:** Complete · **Date:** 2026-10-06 · **Merged:** into local `main` on 2026-10-06, by fast-forward · **Readiness:** not applicable; the migration predates `scripts/readiness.py` · **Plan:** [python-api-migration.md](../plans/python-api-migration.md)

The migration replaced the Express proof of concept with the Python API workspace described in [ADR 0001](../decisions/0001-python-api-and-workspace.md).

This record summarizes the migration's review run and its closeout. The raw Codex reports and the original closeout record are kept privately, outside the repository. The SHA-256 of each is listed below, so their holder can show that this summary matches them. The record cites no commits, because the migration's history was not published ([ADR 0002](../decisions/0002-publish-a-snapshot-with-run-records.md)).

## Reviews

Every pass used the installed Codex plugin's adversarial review, with these settings:

- **Tool:** `codex@openai-codex` 1.0.6, `adversarial-review`, on Codex CLI 0.153.4.
- **Scope:** automatic, on a clean tree, so each pass reviewed the whole branch diff against `main`.
- **Sandbox:** read-only.
- **Model:** `gpt-5.6-sol` at reasoning effort `low`. This is the requested model; the model actually served is not exposed.

| Pass | Verdict | Finding | Disposition | Raw report SHA-256 |
| --- | --- | --- | --- | --- |
| A1 | failed | None. The requested model was not available to the account. | No review took place. | none |
| A2 | failed | None, for the same reason. | No review took place. | none |
| 0 | needs-attention | **High.** Timed-out model requests were retried without idempotency protection, so a paid request could be repeated (`adapters/model/openrouter.py`). | Fixed. A request is retried only when no model can have processed it, and every attempt is accounted for. | `65035fa20a373f719cc6d756d82051388c5d36bdae8b3049649f2b038b007c50` |
| 1 | needs-attention | **High.** A persistence error after commit reported "Nothing was changed", and the commit marker was never reconciled (`application/operations.py`). | Fixed. | `ea837c89ea7e0f5064ab241d2f461fb5d47452aca8348c03d7899ea13760e929` |
| 2 | needs-attention | **Medium.** Recovering a committed operation lost its model-call accounting and notes (`application/operations.py`). | Fixed. | `7c98a39eb5da54b0de75cf4d3bd39dfb087fec2cd51c4077570ae5aab4f6739f` |
| 3 | needs-attention | **Medium.** A failure after the rename of an operation's first save left an active operation with no worker (`application/operations.py`). | Fixed: a save raises only if nothing was written. ADR 0001 accepts one residual: a failed directory sync after the rename is logged, not raised. | `8f75bef7adc28aa49054cf7f5c63ddfb92cce6ce6774d4584de3d88cedfd844c` |
| 4 | needs-attention | **High.** Corrupt operation records were silently skipped instead of entering recovery (`adapters/persistence/files.py`). | Fixed. | `e2a435dfbab4b29801ce423024e338f17b0e32d3168ec68847abf73c809ad982` |
| 5 | needs-attention | **Medium.** An unrelated active operation could switch the displayed project (`features/workspace/use-workspace.ts`). | Fixed. | `42cfb70936d38a96dda82ce337da43abff59b9d690f0c696e3fae16015ea4de4` |
| 6 | needs-attention | **High.** A `busy` response attached the tab to a semantically different operation (`features/workspace/use-workspace.ts`). | Fixed. | `3a251b117dd79856650ca5f7dbf772d2c50e8326418e922167967c2196b66a7d` |
| 7 | needs-attention | **High.** Starting model work is not idempotent. A lost `202`, or a retry after completion, starts another paid call and creates another project (`application/operations.py`). | **Deferred:** a temporary limitation, accepted by the owner for the local single-user proof of concept. Recorded as a known gap in ADR 0001, with the follow-up [idempotent model starts](../specs/idempotent-model-starts.md). | `01e202cdccf8273957394107fb8b5667343438d765b6ba5fe34cca87146d6ea3` |

The raw report for pass 0 was recovered from the transcript of the session that launched it. The others were saved by their session. The original closeout record has SHA-256 `da762c552a03b16aaedfc15ecb9b149a0fe3cc2a0ea747c4a8b8ea7ff97c9ffe`.

**What "fixed" means here:**

- Each fix added or changed regression tests next to its code, and those tests pass.
- Each later pass reviewed the whole branch, including the earlier fixes, and did not raise them again. That is implicit coverage, not a targeted verification of each fix.
- History cannot show that the tests came first. The session record shows a failing regression test before the pass-6 fix. The other fixes were not audited for test-first order.

**Limits of this evidence:**

- The adversarial prompt asks for one strong finding rather than several weak ones, so each pass reported at most one. A pass with one finding does not mean the rest of the diff is clean.
- Every pass ran at reasoning effort `low`.
- The same coordinator wrote each fix and launched the next pass. No independent Claude or human review of the whole migration took place.
- The final pass's `needs-attention` verdict stands. Its only finding is the accepted limitation above.

## Gates

| Gate | Revision | Result |
| --- | --- | --- |
| `TURBO_FORCE=true pnpm check` | the merged revision | Pass, with 0 of 13 tasks cached. API: 191 tests, lines 99.2%, branches 94.4%. Domain: lines 99.4%, branches 96.6%. Web: 47 tests, lines 96.58%. Boundaries: 5 contracts kept, no dependency violations. No contract drift. |
| `pnpm check` | the last source revision | Pass |
| `pnpm e2e` (Playwright and axe, fixture mode) | the last source revision | 5 passed |
| `SMOKE_E2E=1 pnpm docker:smoke` | the last source revision | Pass. Every check printed `ok`, and 5 journeys passed against the containers. |
| GitHub CI | none | Never run |
| Live OpenRouter evaluation | none | Never run: no credentials or budget. See [the observations](../evaluations/live-model-observations.md). |

## Found during closeout

Two defects were found during closeout. Neither blocked the merge, and both were fixed in [the agent workflow run](2026-10-06-agentic-workflow.md), as W1 and W2.

- **The smoke test's hardening checks were not enforced.** A violated check printed nothing instead of failing the run. Every check printed `ok` at the last source revision, so the hardening held there.
- **The environment-upgrade instructions were misleading.** Startup reports retired setting names before it checks values, and `cp .env.example .env` would overwrite an existing `.env`.

## Decisions

- **2026-10-06.** The owner accepted the idempotency gap (pass 7) as a temporary limitation. [Idempotent model starts](../specs/idempotent-model-starts.md) must be implemented before regular live-model use.
- **2026-10-06.** The branch was fast-forwarded into local `main`. The merge conditions held:
  - no unresolved blocking finding;
  - review coverage of the last source change;
  - passing gates;
  - an explicit scope for each deferral.

## Accepted limitations

- Starting model work is not idempotent (pass 7).
- A model attempt in flight when the process dies is not logged. After a restart, the operation is reported as interrupted, without saying that it may have been charged.
- A failed directory sync after a rename is logged, not raised.
- The API runs as a single process.

**Not assessed:** production readiness. The app has no authentication or multi-user isolation, and it binds to loopback.

## Published content

The migration's last reviewed source revision is not published. These folders are unchanged from it in the published tree. Compare them with `git rev-parse HEAD:<folder>`.

| Folder | Git tree hash |
| --- | --- |
| `apps/api/src` | `961d19341bbcc2b8bef1679cd89641db7c865dfd` |
| `apps/api/tests` | `2466ac8a7820d6b5b9cd404932904402e83e9d52` |
| `apps/web` | `0274c97ef0001ecd7bcdc339b6ed1d7c5b115113` |
| `packages` | `b7b3c618737b9a54ca38f7206b94336e5373dbca` |
| `fixtures` | `7a52eeea0cae9a85dc9e2dc2f9876ecc48587639` |
| `.github` | `2301558634d7f97a01f85b3ea4067ecca3ed683a` |

Later changes, all reviewed in the agent workflow run, touched the evaluation docstrings in `apps/api/evals`, the smoke scripts, `README.md`, `AGENTS.md`, `.env.example`, and `package.json`. They also added the workflow scripts, skills, and agents.
