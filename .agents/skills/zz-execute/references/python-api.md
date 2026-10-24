# Python API rules

These rules apply to `apps/api`, a FastAPI and Pydantic service managed by uv. The boundaries are enforced by `lint-imports` and pyright in strict mode, which `pnpm check` runs. The rest are review criteria.

## Layers

- **`domain/` is pure.** It holds no I/O, clock, ids, environment, asyncio, or transport, as the import-linter contracts in `pyproject.toml` require. Effects enter as arguments: `at`, ids, and the proposal.
- **Values are immutable.** Models subclass `domain.model.Value` (frozen Pydantic, camelCase on the wire) or are `@dataclass(frozen=True)`. Collections are tuples. A transition takes a record and returns a new record; it never mutates.
- **Outcomes are typed.** Return explicit types such as `Found`, `Missing`, `Corrupt`, `Rejected`, or `Valid`, and narrow them with `match` or `isinstance`. Do not return `None` or raise to signal an expected case.
- **`application/`** holds the use cases, the ports (`Protocol`s in `ports.py`), and the operation runner. It reaches effects only through ports, and raises `ApplicationError(kind, message)` with a kind from `ErrorKind`.
- **`adapters/`** holds HTTP, file persistence, OpenRouter, and the fixture model. Adapters do not import one another. The HTTP adapter maps each `ErrorKind` to an RFC 9457 `application/problem+json` response.
- **`main.py`** is the only composition root, and **`config.py`** the only place configuration is read. Only `ZIGZAG_*` variables are read, and an unknown one fails startup.

## Product rules in code

- **The model only proposes.** Validate every proposal in the API before any state changes. A quote alone never authorizes a commitment; hedged, conditional, suggested, or negated wording stays a proposal.
- **A choice and its consequences are one decision, saved in one write.** Decisions are append-only: supersede them, never erase them.
- **Every saved content change increments the revision.** A review applies to one exact revision.
- **Unknown stays unknown.** An unknown cost is `unknown`, never zero. A field with no evidence stays empty.
- **Keep fixture scenario terms out of `src/`.** `tests/test_hardcoding.py` enforces this from both sides.

## Contracts

The Pydantic transport models in `adapters/http/schemas.py` are the contract. After changing them or a route, run `pnpm contract` and commit `openapi.json` with the regenerated client. `pnpm contract:check` fails on drift. Additive changes keep stored records loading: optional fields, and `schemaVersion` unchanged unless a migration exists.

## Tests

- pytest runs with `filterwarnings = error` and a 60-second timeout.
- The coverage floors are API lines 85% and branches 80%, and domain 90% for both. `scripts/check_coverage.py` enforces them.
- Prefer the highest stable seam. The HTTP harness in `tests/api/harness.py` runs the real app on a temporary directory with a `ScriptedAssessor`. Application tests use the fakes in `tests/support.py`. Domain tests call transitions directly.
- A failure path, such as a persistence error, a timeout, or a cancellation, gets a test that injects the failure.
- Ruff (line length 120, the rules in `pyproject.toml`) and `ruff format` must pass.
