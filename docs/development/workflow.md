# Development workflow

**Status:** Current · **Updated:** 2026-10-07

This is how a change moves from request to pull request. Every step can be done by hand. The agent skills in `.agents/skills/` guide AI-assisted runs through the same steps. They are guidance; the scripts listed under "Gates" are the enforcement.

```
intake → implementation → deterministic checks → independent reviews → fixes and rechecks → pre-PR readiness
ih-intake   ih-execute        pnpm check (+ gates)    ih-review             ih-execute, ih-review   ih-pre-pr
```

Trivial changes skip the review stages: a typo, or a comment that changes no behavior. If a change has tests to verify, or could change behavior, it goes through the whole workflow.

## Stages

1. **Intake** (`ih-intake`). Take a read-only inventory of the code involved. Choose the smallest document that fits, using [docs/README.md](../README.md). Write numbered acceptance criteria with test levels, and a verification plan. The `spec-reviewer` agent reviews any PRD or spec. The user approves the scope.
2. **Implementation** (`ih-execute`). Make small commits, test-first, with one writer per file. The `python-api-engineer` and `react-ui-engineer` agents each work only inside their own app. In a trusted folder, a hook blocks their Edit and Write tools outside it. The coordinator owns the contract, the generated client, docs, and root configuration.
3. **Deterministic checks.** `pnpm check`, plus the further gates the changed paths require.
4. **Independent reviews** (`ih-review`). A fresh Claude `code-reviewer` and a Codex adversarial review examine the same frozen commit. Neither sees the other's conclusions, and both are read-only. Raw reports and the findings register stay in the git-ignored `.reviews/<run>/`; see [Review records](#review-records).
5. **Fixes and rechecks.** Reproduce each finding in a temporary worktree. Fix it with a regression test, reject it with evidence, or defer it with a scope and a tracking document. Then rerun the gates, and have both reviewers verify the fixes on the new commit.
6. **Pre-PR readiness** (`ih-pre-pr`). `scripts/readiness.py` runs the gates and checks the evidence. Then commit the run record to `docs/records/`, and draft the PR. Pushing and opening the PR are the owner's decisions.

## Gates

The commands are ordinary scripts. CI runs the same ones; see [.github/workflows/ci.yml](../../.github/workflows/ci.yml).

| Command | What it enforces |
| --- | --- |
| `pnpm check` | Lint, format, types, tests with coverage floors, import boundaries, builds, contract drift, and `pnpm workflow:check`. |
| `pnpm workflow:check` | `scripts/check_docs.py`: links, path mentions, status lines, templates, skill symlinks, portability, agent policy, that `.reviews/` stays git-ignored, and that run records name no local path, id, or cost. Also the tests, ruff, and pyright for the workflow scripts and the hook. |
| `pnpm e2e` | Playwright journeys with axe, against the real API in fixture mode. |
| `SMOKE_E2E=1 pnpm docker:smoke` | A fresh-checkout container build, the hardening checks (each fails the run), persistence, and the journeys against the containers. |
| `pnpm readiness --base <sha> --register <file>` | Readiness. It runs the required gates, and checks the review evidence and finding dispositions. It exits 0 only for `READY`. |

`scripts/readiness.py` decides which gates a change needs, from the changed paths. `pnpm check` always runs. `pnpm e2e` runs for changes to the API source, the web app, the generated client, or the fixtures. `pnpm docker:smoke`, with `SMOKE_E2E=1` when e2e also applies, runs for changes to Dockerfiles, Compose, nginx, lockfiles, package manifests, `.env.example`, configuration, or the smoke scripts. `pnpm readiness --plan` prints the decision for the current branch.

### What readiness requires

- The working tree is clean, so the candidate is the committed `HEAD`.
- `claude-code-reviewer` and `codex-adversarial` are always required. `--also-require` can add reviewers, but nothing removes these two.
- For each required reviewer, the complete reports form a chain of `baseline → reviewed_commit` steps from the base to the candidate.
  - A report counts only if its `tool`, `model`, and `invocation` fields are filled.
  - A commit after the last reviewed one counts only if it touches nothing but `docs/records/`.
  - A missing, `incomplete`, or `blocked` reviewer makes the status `INCOMPLETE`.
- Every finding in the register has a valid disposition:
  - `fixed` names a commit on the branch, contained in the candidate, with evidence. The commit must change more than review records, and it must come after the `reviewed_commit` of every report that raised the finding. The check cannot tell whether the commit is relevant to the finding.
  - `rejected` names evidence;
  - `deferred` names a scope and a tracking document that contains the finding's ID.

  An `open` finding makes the status `NOT READY`. Each report's findings must appear in the register.
- Every required gate passes. A failed gate makes the status `NOT READY`. Skipped gates make it `INCOMPLETE`.

A `READY` with deferred findings says so in its title. It also lists every high or critical deferral as needing the owner's acceptance.

### What readiness cannot establish

- **Whether a disposition is right.** Reviewers and the owner judge that.
- **Whether a report is genuine.** Its contents, provenance, and claimed commits are taken as declared. `scripts/claude_review.py` and `scripts/codex_review.py` print evidence blocks filled from the actual run: the session or thread id, the version, the models, and the commits. A reader can trace those ids. Nothing authenticates a report written by hand, though. This is finding X2 in [the agent workflow run record](../records/2026-10-06-agentic-workflow.md), deferred for this local, single-user workflow. The evidence stays in the git-ignored `.reviews/`, so a pull request cannot supply it. The owner accepted this limitation on 2026-10-07.
- **Whether the owner accepted a deferral.** The readiness report flags high and critical deferrals; the acceptance itself lives in the tracking document.

The workflow scripts need the Python pinned in `mise.toml` (3.14). The scope-guard hook runs on Python 3.9 or later, because Claude Code runs it with whatever `python3` is on `PATH`.

## Review records

The repository is public, so it keeps summaries of review runs, not their raw output ([ADR 0002](../decisions/0002-publish-a-snapshot-with-run-records.md)).

| What | Where | Committed |
| --- | --- | --- |
| Raw reviewer reports, the findings register, the readiness output, and the PR draft | `.reviews/<run>/` | No. `.gitignore` excludes it, and it stays on the machine that ran the review. |
| The run record: gates, reviewers, findings and dispositions, decisions, and the SHA-256 of each raw file | `docs/records/YYYY-MM-DD-<slug>.md`, generated by `scripts/run_record.py` in [this format](../templates/run-record.md) | Yes, in a report-only commit |

`scripts/run_record.py` copies structured fields only, never overwrites a record, and refuses to write one that names a local path, a session or thread id, or a cost. `pnpm check` applies the same rule to every run record.

`git clean -x` deletes `.reviews/`, so back it up if the raw reports matter.

## Agents

| Agent | Model | Tools | Role |
| --- | --- | --- | --- |
| `spec-reviewer` | `sonnet` | Read, Grep, Glob | Checks a PRD or spec for scope, contradictions, contracts, and acceptance criteria. |
| `python-api-engineer` | `sonnet` | Read, Grep, Glob, Edit, Write, Bash | Implements API work. Edit and Write are limited to `apps/api/` by a hook. |
| `react-ui-engineer` | `sonnet` | Read, Grep, Glob, Edit, Write, Bash | Implements web work. Edit and Write are limited to `apps/web/` by a hook, and `design-system/ui` stays unmodified. |
| `code-reviewer` | `sonnet` | Read, Grep, Glob | Independent review of a frozen candidate. |

Use a specialist when its scope helps. Do not dispatch every agent for every task.

What was observed with Claude Code 2.1.292 is summarized in [the agent workflow run record](../records/2026-10-06-agentic-workflow.md):

- **Models.** All four agents resolved `sonnet` to `claude-sonnet-5-5`.
- **Tools.** The reviewers resolved to exactly Read, Grep, and Glob. When Bash is present, this build drops Grep and Glob, so the engineers resolved to Read, Edit, Write, and Bash, and they search through Bash.
- **The scope hook needs a trusted folder.** Claude Code skips agent frontmatter hooks when the folder holding the definition has not been trusted, and only logs an error. In a fresh, untrusted checkout, the scope guard is therefore inactive until someone opens the folder in Claude Code and accepts the trust dialog. After that, it blocked out-of-scope writes both for a dispatched subagent and under `--agent`.
- **The hook covers Edit and Write.** Shell commands are not checked; the engineers' instructions limit the shell to running commands.

## Review launchers

- **`scripts/claude_review.py`** runs `claude -p --agent code-reviewer` in a fresh session, with read access to the review inputs.
- **`scripts/codex_review.py`** runs Codex's adversarial review of `--base..HEAD` in a read-only sandbox, through the installed Codex plugin (`codex@openai-codex`, `adversarial-review --wait --base`). If the plugin is missing, it falls back to the authenticated Codex CLI (`codex exec --sandbox read-only`) with explicit adversarial instructions.

Each launcher reviews its own temporary git worktree of `HEAD`, with `docs/records/` removed, so the two can run at the same time.

- **Why a separate checkout.** The Codex plugin's `SessionEnd` hook stops the workspace's Codex runtime whenever any Claude Code session in that workspace ends. In round 2 of this branch's review, that stopped a Codex review that shared the main checkout (finding W4).
- **Why no review records.** The checkout has neither `docs/records/` nor the git-ignored `.reviews/`, so earlier conclusions are not in it (finding D6). This is not isolation:
  - a reviewer can still open the main repository by absolute path, and Codex can read git history, so the prompt's instruction not to read other reviews still matters (E2);
  - reports must be written outside the reviewer's inputs directory, and `claude_review.py` refuses an `--out` inside `--inputs` (E1).

Both launchers print an evidence block filled from the run. Both exit 0 only when a report was produced. Otherwise, including when the checkout cannot be made, they print `status: incomplete`, exit 4, and leave no report file. `codex_review.py` exits 3 when Codex is unavailable, and prints the setup steps. Record that review as `blocked`.

Coding-agent reviews are paid by the reviewer's Claude and Codex accounts. They are separate from the application's live-evaluation budget.
