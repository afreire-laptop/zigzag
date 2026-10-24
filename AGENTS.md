# zigzag

Write the project name in lowercase, `zigzag`, even at the start of a sentence or a heading.

- **Product boundary:** [docs/product/tenet.md](docs/product/tenet.md).
- **Journeys:** [docs/product/journeys.md](docs/product/journeys.md). They are behavioral fixtures, not specifications or hardcoded answers.
- **Architecture:** [ADR 0001](docs/decisions/0001-python-api-and-workspace.md).

## Current milestone

Milestone 1 is a local proof of concept in three parts:

- the ambiguous journey end to end, covering both choice and deferral;
- the clear journey, with no unnecessary questions;
- correcting an answer: selecting another option, answering in the user's own words, or leaving the question open again.

Record live-model results in [docs/evaluations/live-model-observations.md](docs/evaluations/live-model-observations.md), following [the protocol](docs/evaluations/live-model-protocol.md). Implement [idempotent model starts](docs/specs/idempotent-model-starts.md) before regular live-model use.

The next milestone is the changing-brief journey: conflicts, and model-proposed replacement of existing statements. Start it only when the user asks.

## Layout

- `apps/api`: the Python API, in FastAPI and Pydantic, managed by uv. It holds all domain authority.
  - `domain/`: the pure core: the project record, transitions, invariants, proposal validation, handoff rendering, and the project view.
  - `application/`: use cases and ports, the operation runner, and the versioned prompt.
  - `adapters/`: HTTP, file persistence, the OpenRouter client, and the fixture model.
  - `main.py` is the only composition root, and `config.py` the only place configuration is read.
- `apps/web`: React with Vite.
  - `features/`: the two surfaces and their parts.
  - `design-system/ui`: unmodified shadcn output.
  - `platform/`: the only code that talks to the API.
- `packages/api-client`: generated from `apps/api/openapi.json`. Only `pnpm contract` writes its `src/generated`.
- `fixtures/`: journey texts, canned proposals (`journeys.json`), and the legacy goldens the Python domain must reproduce.
- `docs/`: one folder per document type. [docs/README.md](docs/README.md) says which document a change needs, and lists the templates.
- `scripts/`: the gates that `pnpm` and CI run, including the docs and readiness checks; the review launchers; and `run_record.py`, which writes a run's public record.
- `.agents/skills/`: the canonical workflow skills, exposed to Claude Code by relative symlinks in `.claude/skills/`. `.claude/agents/` defines the subagents, and `.claude/hooks/` holds their scope guard.

## Commands

Install the toolchain once with `mise install && pnpm install`. Everything else is a root script:

- `pnpm dev`: runs the API with reload on `127.0.0.1:8000` and the web app on `127.0.0.1:5173`, in fixture mode unless `.env` says otherwise. Run `uv sync --frozen --project apps/api` first.
- `pnpm check`: every deterministic gate: lint, format, types, tests with coverage thresholds, import boundaries, builds, contract drift, and the docs and workflow checks. Run it before claiming completion.
- `pnpm e2e`: the Playwright journeys, with axe, against the real API in fixture mode.
- `pnpm docker:smoke`: runs `cp .env.example .env && docker compose up --build` on a fresh worktree, then checks the stack and its persistence. `SMOKE_E2E=1` also runs the journeys against the containers.
- `pnpm contract`: regenerates `openapi.json` and the client. Run it after changing any Pydantic transport model or route.
- `pnpm readiness --base <sha> --register <file>`: runs the gates the changed paths require, and checks that the review evidence covers `HEAD`. It exits 0 only for `READY`.
- `pnpm eval --budget-usd N --max-calls N`: the live evaluations. They spend money, and never run in CI.

## Workflow

Changes go through intake (`zz-intake`), implementation (`zz-execute`), deterministic checks (`pnpm check` and the gates the changed paths require), independent reviews (`zz-review`), fixes and rechecks (`zz-execute`, then `zz-review`), and pre-PR readiness (`zz-pre-pr`). [docs/development/workflow.md](docs/development/workflow.md) details each stage. The skills guide; the scripts are the gates. Everything builds and tests without an AI tool installed.

## Rules

- **The model only proposes.**
  - Intent changes only through a user action, or through an explicit user instruction recorded with its verbatim quote.
  - Validate every proposal before any state changes.
  - A quote appearing in the text never authorizes a commitment by itself. Hedged, conditional, suggested, or negated wording stays a proposal.
  - Model output never writes files and never marks a revision reviewed.
- **A choice is saved with its consequences.**
  - Save a choice and its intent change as one decision, in one write.
  - Decisions are append-only: supersede them, never erase them. When a later decision replaces only part of an earlier one, show that part as superseded.
- **Reviews are tied to revisions.**
  - Every saved content change increments the revision.
  - A review applies to one exact revision, and an export comes from that same revision.
- **Unknown stays unknown.** An unknown field stays empty, and an unknown cost is labeled unknown. Never invent evidence, rationale, confidence, or cost.
- **The API owns every transition.**
  - The browser renders the project view, including its `actions` flags. From the rest of the repository, it imports only `packages/api-client`.
  - Domain rules live in the API; never re-implement them in TypeScript.
  - Request, response, and event types come from the generated client; never hand-write them.
- **The domain is pure.** Model calls, persistence, the clock, ids, the environment, and transport are effects behind ports. `lint-imports` and dependency-cruiser enforce the boundaries.
- **The API is single-process.** Project locks and operation tracking live in memory, so run one worker.
- **Fixtures stay out of application code.**
  - Keep fixture terms out of `apps/api/src`; a two-sided test enforces this.
  - Label fixture output wherever it appears.
- **Out of scope:**
  - authentication, collaboration, automated research, and downstream execution;
  - multi-agent orchestration, automatic model routing, and classifiers;
  - graph storage, workflow engines, event buses, and generated interfaces.

  Add structure only when a journey behavior needs it.

## Machine-global skills

These optional skills, installed outside the repository, shaped its conventions. Nothing in the repository depends on them. Where one is installed, it covers:

- `codebase-design` and `structure-codebase`: module depth and physical boundaries;
- `api-design`: problem responses and the operation resources;
- `twelve-factor`: configuration and process lifecycle;
- `web-quality-skills:accessibility` and `web-design-guidelines`: focus and contrast;
- `writing-for-agents`: this file, the workflow skills, and the agent definitions;
- `technical-writing`: the documents in `docs/`.
