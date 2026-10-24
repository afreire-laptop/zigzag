---
name: zz-pre-pr
description: Decides whether a zigzag branch is ready for a pull request. Runs the deterministic gates, confirms that the review evidence covers the candidate source revision, commits a run record, and drafts a PR description without publishing. Use when reviewed work is about to become a PR, or when asked whether a branch is ready.
---

# Pre-PR readiness

`scripts/readiness.py` decides readiness. This skill runs it, and reports what it printed.

## Steps

1. **Fix the candidate.** The tree must be clean, so that the candidate is `HEAD`. Set `BASE=$(git merge-base main HEAD)`, and set `RUN` to the run's folder in `.reviews/`, which holds the findings register and the raw reports.
2. **Run the readiness check.** Run `python3 scripts/readiness.py --base $BASE --register $RUN/findings.md --out $RUN/readiness.md`.
   - It runs the gates the changed paths require: always `pnpm check`, plus `pnpm e2e` and `SMOKE_E2E=1 pnpm docker:smoke` when the changed paths require them.
   - It checks that each required reviewer's reports form a complete chain from `BASE` to the candidate, and that every finding has a valid disposition.
     - `claude-code-reviewer` and `codex-adversarial` are always required. `--also-require` adds more, but nothing removes them.
   - It prints `READY`, `INCOMPLETE`, or `NOT READY`, and exits 0 only for `READY`. A `READY` with deferred findings says so in its title. It also lists every high or critical deferral as needing the owner's acceptance.
3. **Act on the result.** On `INCOMPLETE` or `NOT READY`, report the printed reasons as they are. Fix the cause through `zz-execute` or `zz-review`, and run the check again. The evidence only describes what happened. Change it when something new happened, never to make the check pass.
4. **Generate the run record.** Run `python3 scripts/run_record.py --run $RUN --title "<change>" --summary "<one or two sentences>" --out docs/records/YYYY-MM-DD-<slug>.md`.
   - It copies the readiness status and gates, each review's reviewer, tool, model, range, status, and findings, and each finding's line and disposition. It adds the SHA-256 of every raw file. It copies no report text, invocation id, or evidence note.
   - Pass each of the owner's decisions, dated, with `--decision`. Pass anything else the run does not establish with `--not-verified`, such as test-first history that was not observed. The readiness output already names GitHub CI and live-model behavior.
   - It refuses to overwrite a record, and to write one that names a local path, a session or thread id, or a cost. Fix the register or the arguments, never the check.
   - Read the record, then commit it alone, as a report-only commit.
5. **Draft the PR** in `$RUN/pr.md`: a title, and a body with the summary, the verification numbers, a link to the run record, and the deferred items. Pushing and opening the PR are the user's decisions.

**Done when** the run record is committed locally, its status matches the script's output exactly, and the PR draft is in `$RUN/`.
