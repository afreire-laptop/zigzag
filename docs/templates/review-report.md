# <Review>: <reviewer>

**Status:** Complete · **Date:** YYYY-MM-DD

<!-- Keep this report at `.reviews/<run>/<reviewer>-<round>.md`, which is git-ignored; it is never committed, and the run record summarizes it. Paste the evidence block the review launcher printed, or fill it by hand for a human review. Readiness ignores a report whose `tool`, `model`, or `invocation` is empty, and every ID in `findings` must be in the findings register. -->

```
reviewer: <claude-code-reviewer | codex-adversarial | human>
tool: <agent or CLI, with version>
model: <resolved or requested model, or "not exposed">
invocation: <session or thread id, or how a human review was recorded>
reviewed_commit: <full SHA of the frozen candidate>
baseline: <full SHA the review started from>
status: <complete | incomplete | blocked>
findings: <register IDs, or none>
```

## Scope and inputs

<What was reviewed, and what the reviewer received. Confirm that it did not see another reviewer's conclusions.>

## Not examined

<The areas the review did not cover, and its other limits.>

## Report (verbatim)

<The reviewer's report, exactly as produced. Per finding: ID, severity, path:line, trigger or reproduction, impact, and minimal remedy, with hypotheses labeled.>
