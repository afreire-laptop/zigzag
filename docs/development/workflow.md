# Development workflow

**Status:** Current · **Updated:** 2026-10-24

A change moves from request to pull request in six stages, and every step can be done by hand. The agent skills in `.agents/skills/` guide AI-assisted runs through the same steps. They are guidance; the scripts listed under [Gates](#gates) are the enforcement.

```
intake → implementation → deterministic checks → independent reviews → fixes and rechecks → pre-PR readiness
zz-intake   zz-execute        pnpm check (+ gates)    zz-review             zz-execute, zz-review   zz-pre-pr
```

Trivial changes skip the review stages: a typo, or a comment that changes no behavior. If a change has tests to verify, or could change behavior, it goes through the whole workflow.

The workflow scripts need the Python pinned in `mise.toml` (3.14). The scope-guard hook runs on Python 3.9 or later, because Claude Code runs it with whatever `python3` is on `PATH`.

## Stages

1. Intake (`zz-intake`). Take a read-only inventory of the code involved. Choose the smallest document that fits, using [docs/README.md](../README.md). Write numbered acceptance criteria with test levels, and a verification plan. The `spec-reviewer` agent reviews any PRD or spec, and the user approves the scope.
2. Implementation (`zz-execute`). Make small commits, test-first, with one writer per file. The `python-api-engineer` and `react-ui-engineer` agents each work only inside their own app; in a trusted folder, a hook blocks their Edit and Write tools outside it. The coordinator owns the contract, the generated client, docs, root configuration, and `scripts/`.
3. Deterministic checks. Run `pnpm check`, plus the further gates the changed paths require.
4. Independent reviews (`zz-review`). A fresh Claude `code-reviewer` and a Codex adversarial review examine the same frozen commit. Both are read-only, and neither sees the other's conclusions. Raw reports and the findings register stay in the git-ignored `.reviews/<run>/`; see [Review records](#review-records).
5. Fixes and rechecks. Reproduce each finding in a temporary worktree. Fix it with a regression test, reject it with evidence, or defer it with a scope and a tracking document. Then rerun the gates, and have both reviewers verify the fixes on the new commit.
6. Pre-PR readiness (`zz-pre-pr`). `scripts/readiness.py` runs the gates and checks the evidence. Then commit the run record to `docs/records/`, and draft the PR. Pushing and opening the PR are the owner's decisions.

## Gates

The gates are ordinary scripts. CI runs `pnpm check`, `pnpm e2e`, and the container smoke test without `SMOKE_E2E`, on pull requests and on pushes to `main`; see [.github/workflows/ci.yml](../../.github/workflows/ci.yml).

| Command | What it enforces |
| --- | --- |
| `pnpm check` | Lint, format, types, tests with coverage floors, import boundaries, builds, contract drift, and `pnpm workflow:check`. |
| `pnpm workflow:check` | The docs check, `scripts/check_docs.py`, whose checks are listed in [docs/README.md](../README.md#naming-and-checks). Then the tests, ruff, and pyright for the workflow scripts and the hook. |
| `pnpm e2e` | Playwright journeys with axe, against the real API in fixture mode. |
| `SMOKE_E2E=1 pnpm docker:smoke` | A container build from a fresh checkout of the committed `HEAD`, the hardening checks (each fails the run), persistence, and the journeys against the containers. |
| `pnpm readiness --base <sha> --register <file>` | Readiness. It runs the required gates, and checks the review evidence and finding dispositions. It exits 0 only for `READY`. |

`scripts/readiness.py` decides from the changed paths which gates a change needs:

- `pnpm check` always runs.
- `pnpm e2e` runs for changes to the API source, the web app, the generated client, or the fixtures.
- `pnpm docker:smoke` runs for changes to Dockerfiles, Compose, nginx, lockfiles, package manifests, `.env.example`, configuration, or the smoke scripts. It runs with `SMOKE_E2E=1` when `pnpm e2e` also applies.

The exact path lists are `E2E_PATHS` and `SMOKE_PATHS` in that script. `pnpm readiness --base <sha> --plan` prints the decision for the current branch.

### What readiness requires

- The working tree is clean, so the candidate is the committed `HEAD`.
- `claude-code-reviewer` and `codex-adversarial` are always required. `--also-require` can add reviewers, but nothing removes these two.
- For each required reviewer, the complete reports form a chain of `baseline → reviewed_commit` steps from the base to the candidate.
  - A report counts only if its `tool`, `model`, and `invocation` fields are filled.
  - A commit after the last reviewed one counts only if it touches nothing but `docs/records/`.
  - A missing, `incomplete`, or `blocked` reviewer makes the status `INCOMPLETE`.
- Every finding in the register has a valid disposition, and every finding a report lists appears in the register. An `open` finding makes the status `NOT READY`.
  - `fixed` names a commit on the branch, contained in the candidate, with evidence. The commit must change more than review records, and it must come after the `reviewed_commit` of every report that raised the finding. The check cannot tell whether the commit is relevant to the finding.
  - `rejected` names evidence.
  - `deferred` names a scope and a tracking document that contains the finding's ID.
- Every required gate passes. A failed gate makes the status `NOT READY`, and skipped gates make it `INCOMPLETE`.

A `READY` with deferred findings says so in its title. It also lists every high or critical deferral as needing the owner's acceptance.

### What readiness cannot establish

- Whether a disposition is right. Reviewers and the owner judge that.
- Whether a report is genuine. Its contents, provenance, and claimed commits are taken as declared, and nothing authenticates a report written by hand. This is finding X2 in [the agent workflow run record](../records/2026-10-06-agentic-workflow.md), deferred for this local, single-user workflow; the owner accepted the limitation on 2026-10-07.
  - `scripts/claude_review.py` and `scripts/codex_review.py` print evidence blocks filled from the actual run: the session or thread id, the version, the models, and the commits. A reader can trace those ids.
  - The evidence stays in the git-ignored `.reviews/`, so a pull request cannot supply it.
- Whether the owner accepted a deferral. The readiness report flags high and critical deferrals; the acceptance itself lives in the tracking document.
- Whether hosted CI passed, or how a live model behaves. Readiness runs the gates locally, and the gates use fixtures and stubbed providers.

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
| `python-api-engineer` | `sonnet` | Read, Grep, Glob, Edit, Write, Bash | Implements API work. A hook limits Edit and Write to `apps/api/`, except `apps/api/openapi.json`. |
| `react-ui-engineer` | `sonnet` | Read, Grep, Glob, Edit, Write, Bash | Implements web work. A hook limits Edit and Write to `apps/web/`, and `design-system/ui` stays unmodified. |
| `code-reviewer` | `sonnet` | Read, Grep, Glob | Independent review of a frozen candidate. |

Use a specialist when its scope helps. Do not dispatch every agent for every task.

[The agent workflow run record](../records/2026-10-06-agentic-workflow.md) summarizes what was observed with Claude Code 2.1.292:

- All four agents resolved `sonnet` to `claude-sonnet-5-5`.
- The reviewers resolved to exactly Read, Grep, and Glob. When Bash is present, this build drops Grep and Glob, so the engineers resolved to Read, Edit, Write, and Bash, and they search through Bash.
- The scope hook needs a trusted folder. Claude Code skips agent frontmatter hooks when the folder holding the definition has not been trusted, and only logs an error. In a fresh, untrusted checkout, the scope guard is therefore inactive until someone opens the folder in Claude Code and accepts the trust dialog; after that, it blocked out-of-scope writes both for a dispatched subagent and under `--agent`.
- The hook covers Edit and Write. Shell commands are not checked; the engineers' instructions limit the shell to running commands.

## Review launchers

- `scripts/claude_review.py` runs `claude -p --agent code-reviewer` in a fresh session, with read access to the review inputs.
- `scripts/codex_review.py` runs Codex's adversarial review of `--base..HEAD` in a read-only sandbox, through the installed Codex plugin (`codex@openai-codex`, `adversarial-review --wait --base`). If the plugin is missing, or `node` is not on `PATH`, it falls back to the authenticated Codex CLI (`codex exec --sandbox read-only`) with explicit adversarial instructions.

Each launcher reviews its own temporary git worktree of `HEAD`, with `docs/records/` removed, so the two can run at the same time.

The checkout is separate because the Codex plugin's `SessionEnd` hook stops the workspace's Codex runtime whenever any Claude Code session in that workspace ends. In round 2 of the agent workflow review, that stopped a Codex review that shared the main checkout (finding W4).

The checkout has neither `docs/records/` nor the git-ignored `.reviews/`, so earlier conclusions are not in it (finding D6). This is not isolation:

- a reviewer can still open the main repository by absolute path, and Codex can read git history, so the prompt's instruction not to read other reviews still matters (E2);
- reports must be written outside the reviewer's inputs directory, and `claude_review.py` refuses an `--out` inside `--inputs` (E1).

Both launchers print an evidence block filled from the run, and exit 0 only when a report was produced. Otherwise, including when the checkout cannot be made, they print `status: incomplete`, exit 4, and leave no report file. `codex_review.py` exits 3 when Codex is unavailable and prints the setup steps; record that review as `blocked`.

Coding-agent reviews are paid by the reviewer's Claude and Codex accounts. They are separate from the application's live-evaluation budget.
