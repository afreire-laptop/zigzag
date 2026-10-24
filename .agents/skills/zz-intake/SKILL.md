---
name: zz-intake
description: Turns a request, bug report, or existing spec for zigzag into scoped work with acceptance criteria and a verification plan. Use before implementing a change, or when asked to scope, plan, or write a PRD, spec, ADR, or plan.
---

# Intake

The output is a **scope** the user approves before `zz-execute` starts. A scope names the work, its acceptance criteria, its verification plan, and the document it needs, which may be none.

## Steps

1. **Read the boundary.** Read [AGENTS.md](../../../AGENTS.md) for the rules, the current milestone, and what is out of scope. Read [docs/README.md](../../../docs/README.md) for the document types. Then read the request or spec in full. Done when you can state the request in one sentence and say which milestone it serves.
2. **Inventory, read-only.** Find the code, tests, and docs the work touches. For each area, record `existing: path:line` or `new`. `new` must be literally true: search for the behavior before claiming it. An inventory often shrinks the scope. Done when every area the request names has a cited entry.
3. **Classify the request:** bug fix, behavior change, new capability, architectural choice, or docs and workflow only. Work outside the milestone, such as the changing-brief journey, or work on the out-of-scope list, goes back to the user as a question.
4. **Choose the document.** Follow "Choosing a document" in `docs/README.md`, and start from `docs/templates/<type>.md`. A small bug fix needs no document; its failing regression test is the record.
5. **Write the acceptance criteria.** Number them. Each is observable, and names its test level: domain, application, HTTP harness (`apps/api/tests/api/`), Vitest, Playwright, container smoke, or live evaluation. For a bug, criterion 1 is the reproduction: the test that goes **red** on the bug.
6. **Plan the verification.** List the commands. `pnpm check` always runs. `scripts/readiness.py` decides which further gates the changed paths need. "Gates" in [docs/development/workflow.md](../../../docs/development/workflow.md) summarizes them. Add `pnpm contract` when a Pydantic transport model or route changes. A live-model claim needs an evaluation record, never a stub.
7. **Surface ambiguity.** Ask the user about every consequential choice the request leaves open: product meaning, contracts, stored data, cost. Do not choose silently. For a PRD or spec, dispatch the `spec-reviewer` agent with the document path. Address each point it raises, or record why it does not apply.
8. **Get approval.** Present the scope. **Done when** the user approves the scope, the acceptance criteria, and the verification plan, and any document is committed with status `Draft` or `Ready for implementation`.
