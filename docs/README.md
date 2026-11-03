# Documentation

Each document has one job. Put it in the folder for that job, start it from the matching template, and link to other documents instead of restating them.

## Document types

| Type | Folder | Holds | Current documents | Template |
| --- | --- | --- | --- | --- |
| Product principles | `product/` | The product boundary and the tenets that decide trade-offs. | [tenet.md](product/tenet.md) | [product-principles.md](templates/product-principles.md) |
| User journeys | `product/` | Walkthroughs that fix expected behavior. They are behavioral fixtures, not specifications or hardcoded answers. | [journeys.md](product/journeys.md) | [journey.md](templates/journey.md) |
| Product requirements (PRD) | `prds/` | Users, problem, outcomes, scope, and acceptance for a new capability. | None yet | [prd.md](templates/prd.md) |
| Technical specifications | `specs/` | How a change is built: behavior, contracts, data, and verification. | [idempotent-model-starts.md](specs/idempotent-model-starts.md) | [spec.md](templates/spec.md) |
| Architectural decisions (ADR) | `decisions/` | One decision each, with its context and trade-offs. | [0001](decisions/0001-python-api-and-workspace.md), [0002](decisions/0002-publish-a-snapshot-with-run-records.md) | [adr.md](templates/adr.md) |
| Plans | `plans/` | Execution steps and progress for multi-step work. | [python-api-migration.md](plans/python-api-migration.md) | [plan.md](templates/plan.md) |
| Reference | `reference/` | A description of a current format, contract, or architecture that users of it need. | [handoff-format.md](reference/handoff-format.md), [model-work-and-records.md](reference/model-work-and-records.md) | [reference.md](templates/reference.md) |
| Evaluations | `evaluations/` | The protocols for live-model evaluation, and sanitized run evidence. | [live-model-protocol.md](evaluations/live-model-protocol.md), [live-model-observations.md](evaluations/live-model-observations.md) | [evaluation-protocol.md](templates/evaluation-protocol.md), [evaluation-run.md](templates/evaluation-run.md) |
| Run records | `records/` | One run record per review run: a public summary of its gates, reviewers, findings, and dispositions. Raw reports and the findings register stay in the git-ignored `.reviews/`. | [Python API migration](records/2026-10-06-python-api-migration.md), [agent workflow](records/2026-10-06-agentic-workflow.md), [zigzag rename and docs](records/2026-10-24-zigzag-rename-and-docs.md) | [run-record.md](templates/run-record.md); for `.reviews/`: [review-report.md](templates/review-report.md), [findings-register.md](templates/findings-register.md) |
| Development guides | `development/` | How to set up, upgrade, change, check, and review this repository. | [workflow.md](development/workflow.md), [upgrading.md](development/upgrading.md) | [guide.md](templates/guide.md) |

A folder that has no documents yet, like `prds/`, is not created until it gets one.

## Authoritative sources

When two sources disagree, the first one listed for the topic wins. Fix the other one.

| Topic | Source |
| --- | --- |
| Agent and contributor rules | [AGENTS.md](../AGENTS.md). `CLAUDE.md` only imports it. |
| Running and configuring the app | [README.md](../README.md) |
| The HTTP contract | `apps/api/openapi.json`, generated from the Pydantic models. Documents link to it and never restate it. |
| The handoff format | `apps/api/src/zigzag/domain/handoff.py`, then [reference/handoff-format.md](reference/handoff-format.md) |
| Architecture | The accepted ADRs in `decisions/`. A later ADR supersedes an earlier one explicitly. |
| The gates | The scripts in [package.json](../package.json) and `scripts/`. CI and the agent skills call the same scripts. A gate that exists only in prose is not a gate. |

## Status and metadata

Every document except this README and the templates starts with a metadata line that contains `**Status:**`, followed by any type-specific fields. Use absolute dates. Do not invent a date, an approval, a result, or a reviewer; write "unknown" or "not run" instead.

| Type | Status values |
| --- | --- |
| Principles, journeys | Current, Proposed, Superseded |
| PRD, spec | Draft, Ready for implementation, In progress, Implemented, Superseded, Abandoned |
| ADR | Proposed, Accepted, Superseded by NNNN |
| Plan | Active, Done (with the unverified criteria named), Abandoned |
| Reference, guide, protocol | Current, Deprecated |
| Evaluation run, run record | Complete, Incomplete, Blocked |

## Choosing a document

Write the smallest document that the work needs. Decide during intake (`zz-intake`).

| Work | Document |
| --- | --- |
| A small bug fix | None. The failing regression test and the commit message carry it. If the bug came from a review, it also gets a findings-register entry. |
| A behavior change inside existing requirements | A spec, only if it changes a contract, stored data, or more than one module. Otherwise the acceptance criteria go in the plan or the commit. |
| A new capability, or a change to product scope | A PRD, followed by a spec if the design is not obvious. |
| A hard-to-reverse architectural choice, or one with real alternatives | An ADR. |
| Work that spans sessions or several reviewable steps | A plan. |
| A live-model run | An evaluation record. |
| A review run | A committed run record. Its reports and findings register stay in `.reviews/`. |

## Naming and checks

Name ADRs `NNNN-slug.md`, and never renumber one. Name run records `YYYY-MM-DD-slug.md`, and other documents with a short slug.

A run record summarizes, and quotes no reviewer output. The raw reports, which do, stay in `.reviews/`, where the docs check does not look.

`pnpm docs:check` runs `scripts/check_docs.py`, which `pnpm check` also runs through `pnpm workflow:check`. It verifies that:

- relative links and `docs/…` path mentions resolve;
- every document has a status line in its first 12 lines;
- every template is listed above, and has the common status line;
- every skill has valid frontmatter and a relative symlink in `.claude/skills/`;
- skills, agents, hooks, `AGENTS.md`, and `CLAUDE.md` contain no absolute machine path;
- every agent names an explicit model, and the read-only reviewers have only Read, Grep, and Glob;
- raw review output in `.reviews/` stays git-ignored;
- run records name no local path, session or thread id, or cost.
