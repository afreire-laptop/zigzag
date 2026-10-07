# <Review>: <reviewer>

**Status:** Complete · **Date:** YYYY-MM-DD

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

<What was reviewed and what the reviewer received. Confirm it did not see another reviewer's conclusions.>

## Not examined

<Areas outside the review, and its limits.>

## Report (verbatim)

<The reviewer's report exactly as produced. Per finding: ID, severity, path:line, trigger or reproduction, impact,
and minimal remedy, with hypotheses labeled. This report stays in the git-ignored `.reviews/<run>/` and is never
committed. The run record summarizes it.>
