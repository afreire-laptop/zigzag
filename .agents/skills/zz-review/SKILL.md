---
name: zz-review
description: Runs two independent reviews of a frozen zigzag candidate, a fresh Claude code-reviewer and a separate Codex adversarial review, and records their reports, findings, and dispositions. Use after the gates pass, when asked for a review, or to verify fixes to review findings.
---

# Review

Two reviewers examine the same **frozen candidate**, independently: neither sees the other's conclusions, or earlier review reports for this change. Each report records exactly what it covered, so `scripts/readiness.py` can tell whether the evidence still applies.

Raw reports and the findings register stay on this machine, in the run's git-ignored folder `.reviews/<run>/`. Only the run record, written in `zz-pre-pr`, is committed.

## Steps

1. **Freeze the candidate.** Commit, confirm a clean tree, and confirm that `pnpm check` passes on it. Then set:
   - `CANDIDATE=$(git rev-parse HEAD)`;
   - `BASELINE` to `git merge-base main HEAD` for a first review, or to the previous candidate for a fix-verification round;
   - `RUN=.reviews/YYYY-MM-DD-<slug>`, one folder for the whole run, fix-verification rounds included.
2. **Prepare identical inputs** in session scratch space, outside the repository:
   - the requirements: the scope, spec, or acceptance criteria;
   - `git diff --stat $BASELINE $CANDIDATE`;
   - the diff;
   - the gate results.
3. **Launch both reviewers at once.** Each launcher reviews its own temporary checkout of `HEAD`, without `docs/records/`, so a session ending elsewhere cannot stop the review. It prints the evidence block for its report, filled from the run itself, and exits 0 only when a report was produced. Exit 4 means no report: record the attempt as incomplete, and rerun.
   - The checkout hides `docs/records/`, but other reports stay reachable: a reviewer can still open the main repository by absolute path, or read git history. Each reviewer's prompt (for Codex, the focus file) must therefore tell it not to read them.
   - Write each report outside the inputs directory. `claude_review.py` refuses an `--out` inside `--inputs`.
   - **Claude:** run `python3 scripts/claude_review.py --base $BASELINE --prompt-file <prompt> --inputs <scratch>/inputs --out <scratch>/out/claude.md`.
     - It starts a fresh `claude -p --agent code-reviewer` session, whose only tools are Read, Grep, and Glob, and records the session id and models.
     - A `code-reviewer` subagent dispatched from your own session is also independent, but then you fill its evidence block by hand from its transcript.
   - **Codex:** run `python3 scripts/codex_review.py --base $BASELINE --focus-file <requirements and focus> --out <scratch>/out/codex.md`.
     - It runs the installed Codex plugin's adversarial review in a read-only sandbox, or `codex exec --sandbox read-only` when the plugin is missing.
     - Exit 3 means Codex is unavailable: record the review as `blocked`, with the setup steps it prints.
     - Only Codex produces a Codex review. A Claude agent labeled "Codex" is not one.
4. **Write one report per reviewer** at `$RUN/<reviewer>-<round>.md`, started from `docs/templates/review-report.md`. `<reviewer>` is the evidence block's `reviewer` field.
   - Paste the printed evidence block, and replace `findings` with the register IDs the report raised, or `none`. Readiness ignores a report whose `tool`, `model`, or `invocation` field is empty.
   - List what was not examined. Then quote the reviewer's report verbatim in the last section.
   - Link the report from the findings register, `$RUN/findings.md`, started from `docs/templates/findings-register.md`. `readiness.py` and `run_record.py` read only the reports the register links to.
5. **Triage every finding** in the register.
   - **Reproduce it before you act on it,** in a temporary worktree, so the reviewed tree stays untouched: `git worktree add <scratch>/repro $CANDIDATE`.
   - **Give it one disposition,** with its evidence:
     - `fixed`: a regression test and a fix commit, made through `zz-execute`. Readiness requires the fix commit to change more than review records, and to come after the review that raised the finding. It cannot check that the commit is relevant to the finding.
     - `rejected`: the evidence that refutes it. The run record copies this evidence, so it must name no local path, session or thread id, or cost.
     - `deferred`: its scope, plus a tracking document that names the finding's ID. An ADR entry alone fixes nothing. Deferring a high or critical finding needs the owner's acceptance, recorded in the tracking document. Readiness flags these deferrals but cannot verify the acceptance, so asking for it is your job.

   Done when no finding is `open`.
6. **Verify the fixes.** Fixes make a new candidate: repeat steps 1 to 5 for the next round, with `BASELINE` set to the previous candidate and the focus on the fixes. Any later source change invalidates earlier evidence; a commit that touches only `docs/records/` does not.
7. **Check the evidence.** Run `python3 scripts/readiness.py --base $(git merge-base main HEAD) --register $RUN/findings.md --skip-gates`. **Done when** it lists no reason except that the gates were not run; with `--skip-gates`, the status is never `READY`. Next comes `zz-pre-pr`.
