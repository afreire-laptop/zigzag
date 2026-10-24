---
name: zz-execute
description: Implements approved zigzag work in small reviewable commits, test-first, with the repository's own commands. Use when a scope or spec is approved, when fixing a bug or a review finding, or when dispatching the python-api-engineer or react-ui-engineer agents.
---

# Execute

Start from an approved scope with numbered acceptance criteria. If there is none, run `zz-intake` first.

## Steps

1. **Slice the work.** Each step is one commit that leaves `pnpm check` green. The usual order follows the layers: domain, then application, then adapters and HTTP, then `pnpm contract`, then web.
2. **Assign ownership.** At any moment, each file has one writer.
   - The `python-api-engineer` owns `apps/api/**`. The `react-ui-engineer` owns `apps/web/**`.
   - The coordinator owns everything shared: `apps/api/openapi.json` and `packages/api-client/src/generated/**`, which only `pnpm contract` writes, plus `docs/`, `AGENTS.md`, root configuration, and `scripts/`.
   - Run two agents at once only if their paths are disjoint and neither needs the other's output. Web work after a contract change waits for `pnpm contract`.
   - Give each agent its paths, its acceptance criteria, and the exact verification commands.
3. **Go red, then green.** For each criterion, write the test at the highest stable seam. Run it, and watch it fail for the stated reason. Then write the least code that makes it pass, and refactor while it stays green. Record what actually happened. "Test written first, observed red" and "characterization test added after the code" are both honest. Only the first one is test-first.
   - API: `pnpm --filter @zigzag/api exec uv run --frozen pytest tests/<file> -k <name>`
   - Web: `pnpm --filter @zigzag/web exec vitest run <path>`
   - Full: `pnpm check`. Run `pnpm contract` after any Pydantic transport model or route changes.
4. **Follow the layer rules.** Read [references/python-api.md](references/python-api.md) before changing `apps/api`. Read [references/react-ui.md](references/react-ui.md) before changing `apps/web`.
5. **Commit.** Read the staged diff, then commit with a conventional message in the style of `git log`. Commit locally only. Pushing and publishing are the user's decisions.

**Done when** every acceptance criterion has a passing test, or a named manual or live check marked *not run*; `pnpm check` passes; and the work is committed with a clean tree. Next comes `zz-review`.
