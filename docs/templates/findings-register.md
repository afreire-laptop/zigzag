# <Change>: findings register

**Status:** Incomplete · **Updated:** YYYY-MM-DD · **Candidate:** <SHA> · **Baseline:** <SHA>

<!-- Keep this register at `.reviews/<run>/findings.md`, which is git-ignored; the run record summarizes it. `scripts/readiness.py` and `scripts/run_record.py` read only the review reports this register links to, and read the table by its column names. The run record copies Source as written, so make it plain text, not a link. -->

Reports:

- <a relative link to each review report of this run, such as `[claude-code-reviewer-1.md](claude-code-reviewer-1.md)`>

One row per finding, with a unique ID. Severity is `critical`, `high`, `medium`, or `low`. Dispositions are `open`, `fixed`, `rejected`, and `deferred`, and each one except `open` needs evidence:

- `fixed`: the fix commit in Fix, made after the review that raised the finding; the review or check that verified it in Evidence.
- `rejected`: the evidence that refutes the finding, in Evidence.
- `deferred`: its scope in Evidence, and in Tracking a document that names the finding's ID. A high or critical deferral also needs the owner's acceptance, recorded in that document.

| ID | Severity | Source | Finding | Disposition | Fix | Evidence | Tracking |
| --- | --- | --- | --- | --- | --- | --- | --- |
| F1 | high | <reviewer and round> | <one line> | open | | | |
