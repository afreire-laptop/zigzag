# zigzag

Product boundary: [docs/product/tenet.md](docs/product/tenet.md). Behavioral fixtures (not specifications or hardcoded answers): [docs/product/journeys.md](docs/product/journeys.md). Architecture: [docs/decisions/0001](docs/decisions/0001-python-api-and-workspace.md).

## Current milestone

Milestone 1, a local proof of concept, has three parts:

- The ambiguous journey end to end, covering both choice and deferral.
- The clear journey with no unnecessary questions.
- Correcting an answer: selecting another option, answering in the user's own words, or leaving the question open again.

Live-model results go in [docs/evaluations/live-model-observations.md](docs/evaluations/live-model-observations.md), following [the protocol](docs/evaluations/live-model-protocol.md). Implement [idempotent model starts](docs/specs/idempotent-model-starts.md) before regular live-model use.

The next milestone is the changing-brief journey: conflicts, and model-proposed replacement of existing statements. Do not start it unless asked.

## Layout

- `apps/api`: the Python API, built with FastAPI and Pydantic and managed by uv. It holds all domain authority.
  - `domain/`: the pure core. This is where the project record, transitions, invariants, proposal validation, handoff rendering, and the project view live.
  - `application/`: use cases and ports, the operation runner, and the versioned prompt.
  - `adapters/`: HTTP, file persistence, the OpenRouter client, and the fixture model.
  - `main.py`: the only composition root.
  - `config.py`: the only place configuration is read.
- `apps/web`: React with Vite.
  - `features/` holds the two surfaces and their parts.
  - `design-system/ui` holds unmodified shadcn output.
  - `platform/` is the only code that talks to the API.
- `packages/api-client`: generated from `apps/api/openapi.json`. Do not edit `src/generated`.
- `fixtures/`: journey texts, canned proposals (`journeys.json`), and the legacy goldens that the Python domain must reproduce.
- `docs/`: one folder per document type. [docs/README.md](docs/README.md) says which document a change needs, and has the templates.
- `scripts/`: the gates that `pnpm` and CI run, including the docs check and the readiness check. Also the review launchers, and `run_record.py`, which writes a run's public record.
- `.agents/skills/`: the canonical workflow skills (`zz-intake`, `zz-execute`, `zz-review`, `zz-pre-pr`). `.claude/skills/` holds relative symlinks to them. `.claude/agents/` defines the subagents, and `.claude/hooks/` their scope guard.

## Commands

Install the toolchain once with `mise install && pnpm install`. Everything else is a root script:

- `pnpm dev`: runs the API with reload on `127.0.0.1:8000` and the web app on `127.0.0.1:5173`, in fixture mode unless `.env` says otherwise. Run `uv sync --frozen --project apps/api` first.
- `pnpm check`: runs every deterministic gate: lint, format, types, tests with coverage thresholds, import boundaries, builds, contract drift, and the docs and workflow checks. Run it before claiming completion.
- `pnpm e2e`: runs the Playwright journeys, with axe, against the real API in fixture mode.
- `pnpm docker:smoke`: runs `cp .env.example .env && docker compose up --build` on a fresh worktree, then checks the stack and its persistence. Set `SMOKE_E2E=1` to also run the journeys against the containers.
- `pnpm contract`: regenerates `openapi.json` and the client. Run it after changing any Pydantic transport model or route.
- `pnpm readiness --base <sha> --register <file>`: runs the gates the changed paths require, and checks that the review evidence covers `HEAD`. It exits 0 only for `READY`.
- `pnpm eval --budget-usd N --max-calls N`: runs the live evaluations. These spend money and are never part of CI.

## Workflow

Changes go through intake, implementation, deterministic checks, independent reviews, fixes and rechecks, and pre-PR readiness. The steps are in [docs/development/workflow.md](docs/development/workflow.md), and each has a skill. The skills are guidance; the scripts are the gates. Everything builds and tests without an AI tool installed.

## Rules

- **The model only proposes.**
  - Intent changes only through user actions, or through explicit user instructions recorded with a verbatim quote.
  - Validate every proposal before changing state.
  - A quote appearing in the text does not authorize a commitment. Hedged, conditional, suggested, or negated wording stays a proposal.
  - Model output never writes files and never marks a revision reviewed.
- **Choices are saved with their consequences.**
  - Save a choice and its intent change as one decision, in one write.
  - Decisions are append-only: supersede them, never erase them. When a later decision replaces only part of an earlier one, that part is shown as superseded.
- **Reviews are tied to revisions.**
  - Any saved content change increments the revision.
  - A review applies to one exact revision, and exports come from that same revision.
- **Unknown stays unknown.** Do not invent evidence, rationale, confidence, or cost. Unknown fields stay empty; unknown cost is labeled unknown.
- **The API owns every transition.**
  - The browser renders the project view, including its `actions` flags, and imports only `packages/api-client`.
  - Do not re-implement domain rules in TypeScript. Do not hand-write request, response, or event types.
- **The domain is pure.** Model calls, persistence, the clock, ids, the environment, and transport are effects behind ports. `lint-imports` and dependency-cruiser enforce the boundaries.
- **The API is single-process.** Project locks and operation tracking live in memory, so run one worker.
- **Fixtures stay out of application code.**
  - Keep fixture terms out of `apps/api/src`. A two-sided test enforces this.
  - Label fixture output wherever it appears.
- **Out of scope:**
  - authentication, collaboration, automated research, and downstream execution;
  - multi-agent orchestration, automatic model routing, and classifiers;
  - graph storage, workflow engines, event buses, and generated interfaces.

  Add structure only when a journey behavior needs it.

## Skills consulted

These are optional machine-global agent skills that informed the migration. Nothing in the repository depends on them.

- `codebase-design` and `structure-codebase`: module depth and physical boundaries.
- `api-design`: problem responses and the operation resources.
- `twelve-factor`: configuration and process lifecycle.
- `web-quality-skills:accessibility` and `web-design-guidelines`: focus and contrast.
- `writing-for-agents`: this file.
