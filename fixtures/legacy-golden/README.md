# Legacy goldens

Captured on 2026-10-06 from the Express POC (commit 652a024) by a temporary script, `scripts/capture-legacy-golden.ts`. The script was removed with the legacy implementation; see commit 121d87d for its source. Each scenario file lists the steps with fixed timestamps and ids, then a snapshot after every step:

- the exact stored file;
- the current Markdown and JSON exports;
- the review diff;
- validation notes.

`validation.json` records how the legacy validator treated untrusted model output.

The Python domain replays these steps and must reproduce the snapshots, with two intended differences:

- **The format identifier.** The captures predate the rename to zigzag, so their exports name the format `intent-harness.handoff/v0`. The tests replace it with the current identifier wherever the current code renders the export. A legacy record's reviewed copies keep the old identifier.
- **`ambiguous-deferred-by-reply-then-selected`.** In the legacy output, a deferral recorded inside a reply still reads as current after the question is answered (audit finding F3). The corrected behavior is asserted separately in the API tests.
