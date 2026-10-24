# Legacy goldens

These files record what the Express POC did for a set of scenarios. The Python domain replays the same steps and must reproduce the snapshots (`apps/api/tests/domain/test_legacy_goldens.py`), and records the POC wrote must load and export unchanged (`apps/api/tests/adapters/test_persistence.py`).

Each scenario file lists the steps with fixed timestamps and ids, then a snapshot after every step:

- the exact stored file;
- the current Markdown and JSON exports;
- the review diff;
- validation notes.

`validation.json` records how the legacy validator treated untrusted model output.

## Intended differences

The replay must match the snapshots except in two places:

- The format identifier. The captures predate the rename to zigzag, so their exports name the format `intent-harness.handoff/v0`. The tests replace it with the current identifier wherever the current code renders the export. A legacy record's reviewed copies keep the old identifier.
- The scenario `ambiguous-deferred-by-reply-then-selected`. In the legacy output, a deferral recorded inside a reply still reads as current after the question is answered (audit finding F3). The corrected behavior is asserted separately in the API tests.

In `validation.json`, the `missing fields` case is compared without its issue messages, because schema wording differs between Zod and Pydantic.

## How they were captured

A temporary script, `scripts/capture-legacy-golden.ts`, captured them on 2026-10-06 from the Express POC (commit 652a024). The script was removed with the legacy implementation; see commit 121d87d for its source. Both commits are in the development history before publication, which is not published ([ADR 0002](../../docs/decisions/0002-publish-a-snapshot-with-run-records.md)).
