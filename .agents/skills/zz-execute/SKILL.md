---
name: zz-execute
description: Implements approved zigzag work test-first, in small commits that each keep pnpm check green. Use when a scope or spec is approved, when fixing a bug or a review finding, or when dispatching the python-api-engineer or react-ui-engineer agents.
---

# Execute

Start from an approved scope with numbered acceptance criteria. Without one, run `zz-intake` first.

A dispatched `python-api-engineer` or `react-ui-engineer` runs steps 3 and 4 inside its own paths. Slicing, assignment, and commits belong to the coordinator.

## Steps

1. **Slice the work.** Each slice is one commit that leaves `pnpm check` green. The usual order follows the layers: domain, application, adapters and HTTP, `pnpm contract`, then web.
2. **Assign ownership.** At any moment, each file has one writer.
   - The `python-api-engineer` owns `apps/api/**`. The `react-ui-engineer` owns `apps/web/**`.
   - The coordinator owns everything shared: `apps/api/openapi.json` and `packages/api-client/src/generated/**`, which only `pnpm contract` writes, plus `docs/`, `AGENTS.md`, root configuration, and `scripts/`.
   - Run two agents at once only when their paths are disjoint and neither needs the other's output. Web work after a contract change waits for `pnpm contract`.
   - Give each agent its paths, its acceptance criteria, and the exact verification commands.
3. **Go red, then green,** one criterion at a time. Write the test at the highest stable seam, run it, and watch it go **red** for the stated reason. Then write the least code that turns it green, and refactor while it stays green.
   - API: `pnpm --filter @zigzag/api exec uv run --frozen pytest tests/<file> -k <name>`
   - Web: `pnpm --filter @zigzag/web exec vitest run <path>`
   - Full: `pnpm check`. Run `pnpm contract` after changing a Pydantic transport model or route.

   Record what actually happened: "test written first, observed red" or "characterization test added after the code". Both are honest; only the first is test-first.
4. **Follow the layer rules.** Before changing `apps/api`, read [references/python-api.md](references/python-api.md). Before changing `apps/web`, read [references/react-ui.md](references/react-ui.md).
5. **Commit.** Read the staged diff, then commit with a conventional message in the style of `git log`. Commit locally only: pushing and publishing are the user's decisions.

**Done when** every acceptance criterion has a passing test, or a named manual or live check marked *not run*; `pnpm check` passes; and the work is committed with a clean tree. Next comes `zz-review`.
