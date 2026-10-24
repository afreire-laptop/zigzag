---
name: zz-review
description: Runs independent reviews of a committed zigzag candidate, a fresh Claude code-reviewer and a separate Codex adversarial review, and records their reports, findings, and dispositions. Use after the gates pass, when asked for a review, or to verify fixes to review findings.
---

# Review

Two reviewers examine the same frozen candidate, independently. Each report records exactly what it covered, so `scripts/readiness.py` can tell whether the evidence still applies.

Raw reports and the findings register stay in the run's git-ignored folder, `.reviews/<run>/`, on this machine. Only the run record, written in `zz-pre-pr`, is committed.

## Steps

1. **Freeze the candidate.** Commit, and confirm a clean tree. Set `CANDIDATE=$(git rev-parse HEAD)`. Set `BASELINE` to `git merge-base main HEAD` for a first review, or to the previously reviewed commit for a fix-verification round. `pnpm check` must pass on the candidate first. Set `RUN=.reviews/YYYY-MM-DD-<slug>` for the whole run, including its fix-verification rounds.
2. **Prepare identical inputs** in session scratch space, outside the repository:
   - the requirements, meaning the scope, spec, or acceptance criteria;
   - `git diff --stat $BASELINE $CANDIDATE`;
   - the diff;
   - the gate results.

   Neither reviewer sees the other's conclusions or earlier review reports for this change.
3. **Launch both reviewers at once.** Each launcher reviews its own temporary checkout of `HEAD`, which has no `docs/records/`. A session ending elsewhere therefore cannot stop the review.
   - The checkout does not make other reports unreachable: a reviewer can still open the main repository by absolute path, or read git history. Keep the prompt's instruction not to read them.
   - Write each report outside the inputs directory. `claude_review.py` refuses an `--out` inside `--inputs`.
   - Each launcher prints the evidence block for its report, filled from the run itself, and exits 0 only when a report was produced.
   - **Claude:** run `python3 scripts/claude_review.py --base $BASELINE --prompt-file <prompt> --inputs <scratch>/inputs --out <scratch>/out/claude.md`.
     - It starts a fresh `claude -p --agent code-reviewer` session, whose only tools are Read, Grep, and Glob, and records the session id and models.
     - A `code-reviewer` subagent dispatched from your own session is also independent. Its evidence block, however, must then be filled by hand from its transcript.
   - **Codex:** run `python3 scripts/codex_review.py --base $BASELINE --focus-file <requirements and focus> --out <scratch>/out/codex.md`.
     - It uses the installed Codex plugin's adversarial review in a read-only sandbox. If the plugin is missing, it falls back to `codex exec --sandbox read-only`.
     - Exit 3 means Codex is unavailable: record the review as `blocked`, with the setup steps it prints. Exit 4 means no report was produced: record the attempt, and rerun.
     - A Claude agent labeled "Codex" is not a Codex review.
4. **Write one report per reviewer.** Name it `$RUN/<reviewer>-<round>.md` and start from `docs/templates/review-report.md`.
   - Paste the printed evidence block, and replace `findings` with the register IDs the report raised, or `none`.
   - Readiness ignores a report whose `tool`, `model`, or `invocation` field is empty.
   - List what was not examined. Then quote the report verbatim in the last section.
5. **Triage each finding** in the register `$RUN/findings.md`, started from `docs/templates/findings-register.md`.
   - **Reproduce it before you act on it,** in a temporary worktree: `git worktree add <scratch>/repro $CANDIDATE`. The reviewed tree stays untouched.
   - **Give each finding one disposition:**
     - `fixed`: a regression test and a fix commit, through `zz-execute`. Readiness requires the fix commit to change more than review records, and to come after the review that raised the finding. It cannot check that the commit is relevant to the finding.
     - `rejected`: the evidence that refutes it;
     - `deferred`: its scope, plus a tracking document that names the finding's ID.
       - An ADR entry alone fixes nothing.
       - Deferring a high or critical finding needs the user's acceptance, recorded in the tracking document. Readiness flags these deferrals, but it cannot verify the acceptance; asking for it is your job.
6. **Verify the fixes.** Fixes make a new candidate. Run both reviewers again, with `BASELINE` set to the previous candidate and the focus on the fixes. A later source change invalidates earlier evidence. A commit that touches only `docs/records/` does not.
7. **Check the evidence.** **Done when** `python3 scripts/readiness.py --base <merge-base> --register $RUN/findings.md --skip-gates` reports no evidence gaps. Next comes `zz-pre-pr`.
