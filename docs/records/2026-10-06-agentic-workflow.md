# Agent workflow and documentation: run record

**Status:** Complete · **Date:** 2026-10-06 to 2026-10-07 · **Readiness:** READY, with 1 deferred finding not fixed · **Guide:** [workflow.md](../development/workflow.md)

This change classified `docs/` by document type, with templates and a docs check. It added the workflow skills, the agents, the scope-guard hook, and the gates: `scripts/readiness.py`, the review launchers, and `scripts/check_docs.py`. It closed out [the migration](2026-10-06-python-api-migration.md), and specified [idempotent model starts](../specs/idempotent-model-starts.md).

This record summarizes the run. The raw reports, the findings register, the readiness report, and the tool verification record are kept privately, outside the repository. The SHA-256 of each is listed below. The record cites no commits, because the history of this run was not published ([ADR 0002](../decisions/0002-publish-a-snapshot-with-run-records.md)).

## Gates

All gates ran on the final candidate, which changed only review records after the final reviewed source.

| Gate | Result |
| --- | --- |
| `TURBO_FORCE=true pnpm check` | Pass, with 0 of 13 Turbo tasks cached. API: 191 tests; API lines 99.2% and branches 94.4%; domain lines 99.4% and branches 96.6%. Web: 47 tests in 11 files. No contract drift. Workflow scripts: 83 tests, plus ruff, pyright strict, and the docs check. |
| `pnpm docker:smoke` | Pass. All 12 stack checks, all 5 hardening checks (now enforced), and the persistence checks across a restart and a recreate printed `ok`. |
| Clean checkout | Pass: a fresh clone, `pnpm install --frozen-lockfile`, `uv sync --frozen --project apps/api`, and `TURBO_FORCE=true pnpm check`. This is a local proxy for the CI quality job, not GitHub CI. |
| `pnpm e2e` | Not required: no API source, web, client, or fixture path changed. |
| `scripts/readiness.py` | READY, with 1 deferred finding not fixed. |

## Reviews

Two reviewers ran five rounds, independently. From round 3 on, they ran at the same time, each from its own checkout without the review records. Rounds 2 to 5 verified the previous round's fixes.

- **Claude:** Claude Code 2.1.292, `claude -p --agent code-reviewer`, model `claude-sonnet-5-5`.
- **Codex:** the Codex plugin `codex@openai-codex` 1.0.6, `adversarial-review`, on Codex CLI 0.153.4, in a read-only sandbox. The requested model was `gpt-5.6-sol` at reasoning effort `low`; the model actually served is not exposed.

| Round | Reviewer | Status | Findings | Raw report SHA-256 |
| --- | --- | --- | --- | --- |
| 1 | Claude | complete | C1–C4 | `7f5c6403398c5622f5712fa51412aa14bd137e03d86fe21a6c806bd5129e3cf1` |
| 1 | Codex | complete | X1–X3 | `727cdecc2ed74cbc6be1b1539cd1726db0178488a718a8a1d1fc5a38b9d9dfde` |
| 2 | Claude | complete | D1–D6 | `1c55fb2090d1fbb3c0de26ab17e3240d34a655d54df39ba108a115e7039ec457` |
| 2 | Codex | incomplete: a concurrent Claude session ending stopped it (W4); two focused probes completed | Y1, Y2 | `c2993c0f4d792a1894eec57c837efa954f51f9442fb7b6f42970723e0b084194` |
| 3 | Claude | complete | E1–E4 | `73a6dd00366ea246f7de0c867b8989dc991d04f302758e1ff5ab6947875c00ce` |
| 3 | Codex, covering rounds 2 and 3 | complete; approve | none | `37052d2869026836e55f9cdd8fe16ee4982de67362b52a78f346a3d14b914905` |
| 4 | Claude | complete | F1, F2 | `147f47a7bbed5b92f662caa484f9de6346c2cb92008d68c87a28ca93abfed2bf` |
| 4 | Codex | complete | V1 | `ad0a6489e75b04fa17845f606bbc81ff91ca9a755ce274d99ef0c64ca6ca625d` |
| 5 | Claude | complete; approve | none | `5084b264edf0afeccc8714b12589eaf2144862a9e0fad24b6650ba81508cb6fd` |
| 5 | Codex | complete; approve | none | `29d40989f306cf3154f5a63945822d766a07eeae30a23e05f1d81672f3ab5e4e` |

The other private records of this run:

| Record | SHA-256 |
| --- | --- |
| Findings register | `469c1c14ef2dff2fb72cd082fcb6121f3eadb7762ddbe804a30a4864361a16a6` |
| Readiness report | `c1a17e93446c117d36745595b22e64b0b39e2aab4a27c9edeb42e585662b603f` |
| Tool verification record | `c421d7ced13c61093e86cd710149ef009ec7d6a2a68cbebcd3565af989420e36` |

## Findings

Every finding was reproduced in a temporary worktree before triage. Every fix has a regression test.

| ID | Severity | Source | Finding | Disposition |
| --- | --- | --- | --- | --- |
| W1 | medium | Coordinator, migration closeout | The smoke test's hardening checks did not fail the run when violated. | fixed |
| W2 | low | Coordinator, migration closeout | The README's environment-upgrade text was misleading, and `cp .env.example .env` overwrote an existing `.env`. | fixed |
| C1 | medium | Claude, round 1 | The scope guard failed open: a crash, or a missing or old interpreter, exited nonzero but not 2, which does not block. | fixed |
| C2 | low | Claude, round 1 | Owner acceptance of a high or critical deferral was prose only. | fixed |
| C3 | low | Claude, round 1 | A `fixed` disposition could cite any ancestor commit, even the base. | fixed |
| C4 | low | Claude, round 1 | Readiness did not say that report contents are taken as declared. | fixed |
| X1 | high | Codex, round 1 | An empty or partial reviewer list removed the mandatory reviewers. | fixed |
| X2 | high | Codex, round 1 | A hand-written report with plausible provenance counts as review evidence; nothing local authenticates it. | **deferred** |
| X3 | medium | Codex, round 1 | The review-report template had no `findings` field. | fixed |
| W3 | medium | Coordinator, round 1 | The Codex launcher exited 0 when the run stopped without a report. | fixed |
| D1 | low | Claude, round 2 | A duplicated hook test case, and no real check of Python 3.9 compatibility. | fixed |
| D2 | low | Claude, round 2 | A docs-only commit satisfied the fix-commit rule. | fixed |
| D3 | low | Claude, round 2 | The `codex exec` fallback could report a stale or partial output file as complete. | fixed |
| D4 | low | Claude, round 2 | The Claude launcher could leave a stale report beside an incomplete status. | fixed |
| D5 | low | Claude, round 2 | A test compared report text through `Path()`, which normalizes it. | fixed |
| D6 | low | Claude, round 2 | The reviewer's isolation from review records rested only on the prompt. | fixed |
| Y1 | high | Codex, round 2 probe | A `fixed` finding could cite a commit older than the review that raised it. | fixed |
| Y2 | medium | Codex, round 2 probe | The docs check's review-record exemption skipped more than verbatim quotations. | fixed |
| W4 | medium | Coordinator, round 2 | A Claude session ending in the workspace stopped a running Codex plugin review. | fixed |
| E1 | low | Claude, round 3 | The skill put reports where the reviewer could read them. | fixed |
| E2 | low | Claude, round 3 | The docs overstated the review checkout's isolation. | fixed |
| E3 | low | Claude, round 3 | A failed `git worktree add` raised a traceback instead of reporting an incomplete review. | fixed |
| E4 | low | Claude, round 3 | A log from an earlier run could remain beside an incomplete attempt. | fixed |
| F1 | medium | Claude, round 4 | The launchers never created the output directory, so a finished paid review was lost on write. | fixed |
| F2 | low | Claude, round 4 | A failed `git worktree add` leaked its temporary directory. | fixed |
| V1 | medium | Codex, round 4 | A run that printed a report but exited nonzero kept the report while saying incomplete. | fixed |

**X2, deferred.**

- **Mitigations:**
  - a report counts only with its `tool`, `model`, and `invocation` fields filled;
  - the launchers fill those fields from the actual run;
  - [the workflow guide](../development/workflow.md) states the limit.
- **Scope:** this local, single-user workflow. Since publication, review evidence stays in the git-ignored `.reviews/`, so a pull request cannot supply it.
- **Owner's acceptance:** given on 2026-10-07.

## Tool verification

These were observed with Claude Code 2.1.292 and Codex CLI 0.153.4 on 2026-10-06.

- **Discovery from a fresh clone.** Codex listed the four `ih-*` skills from `.agents/skills`. Claude Code's session init listed the four agents and the four skills.
- **`claude plugin validate`** passed a deliberately malformed agent file, so its result is not used as evidence.
- **Models.** All four agents resolved `sonnet` to `claude-sonnet-5-5`.
- **Tools.** The reviewers resolved to Read, Grep, and Glob. With Bash present, the engineers lost Grep and Glob.
- **The scope-guard hook.**
  - In a trusted folder, it blocked an out-of-scope write and allowed an in-scope one, both under `--agent` and as a dispatched subagent.
  - In an untrusted fresh clone, it did not run.

## Decisions

- **2026-10-07.** The owner merged the branch into local `main` without a pull request, because the remote had no code.
- **2026-10-07.** The owner chose to publish the repository as one snapshot commit, with run records in place of raw reviews ([ADR 0002](../decisions/0002-publish-a-snapshot-with-run-records.md)).
- **2026-10-07.** The owner accepted X2 as a limitation of this local, single-user workflow.

## Not verified

- **GitHub CI.** It had never run before publication.
- **Live OpenRouter behavior.** The gates use fixtures and stubbed transports.
- **The scope-guard hook in untrusted folders,** where Claude Code skips it.
- **Test-first history.**
  - The workflow scripts' first tests were characterization tests, written after the scripts.
  - The smoke-hardening fix was shown failing against the old code only after the fix had been written.
  - The test for the first docs-check exemption was written alongside the change.
  - Every later fix was written test-first, with the failing test observed.

## Published content

The final reviewed source is not published. These folders are unchanged from it in the published tree. Compare them with `git rev-parse HEAD:<folder>`.

| Folder | Git tree hash |
| --- | --- |
| `apps` | `0f202cb7b30909f948d662bc42bfb48707c120a9` |
| `packages` | `b7b3c618737b9a54ca38f7206b94336e5373dbca` |
| `fixtures` | `7a52eeea0cae9a85dc9e2dc2f9876ecc48587639` |
| `.claude` | `d64d5eb94cf376d26a9eb71760b641e6ec6aad9c` |
| `.github` | `2301558634d7f97a01f85b3ea4067ecca3ed683a` |

**Changed after review, and not reviewed.** The publication cleanup changed the following, and no reviewer covered it:

- `docs/`: the raw review records became run records, in `docs/records/` (formerly `docs/reviews/`); ADR 0002; and the references to other projects were removed;
- the `ih-review` and `ih-pre-pr` skills, and `docs/development/workflow.md`, which now keep raw output in `.reviews/` and generate run records;
- `scripts/run_record.py`, the run-record generator, with its tests;
- `scripts/readiness.py`: the record paths, a shared `linked_reports`, each finding's source and text, pipes escaped in gate results, and a test that evidence kept in `.reviews/` counts;
- `scripts/check_docs.py`: rules that keep `.reviews/` git-ignored and run records free of local paths, ids, and costs, and the removal of the exemption for verbatim quotations;
- the folder name in `scripts/review_checkout.py` and the launchers' docstrings;
- two launcher tests, which now use synthetic session and thread ids;
- `.gitignore`, `LICENSE`, `README.md`, and `AGENTS.md`.
