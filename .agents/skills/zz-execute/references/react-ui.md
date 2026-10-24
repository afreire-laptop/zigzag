# React UI rules

These rules apply to `apps/web`: React 19, Vite, strict TypeScript, Tailwind, and shadcn/ui. The boundaries are enforced by dependency-cruiser (`dependency-cruiser.config.cjs`), Biome, and `tsc`, which `pnpm check` runs. The rest are review criteria.

## Boundaries

- **`platform/` is the only code that talks to the API.** It uses the generated SDK from `@zigzag/api-client`, validated by the generated Zod schemas. It imports no UI.
- **`features/`** holds the surfaces and their parts: `intake`, `working-brief`, `decision`, `review`, and `workspace`. Features do not import `app/`.
- **`design-system/ui` is unmodified shadcn output.** Do not edit it. Compose it, or add a product-agnostic component beside it, such as `status-pill.tsx`.
- **Nothing hand-written for the API.** Request, response, and event types come from the generated client. After an API change, the coordinator runs `pnpm contract`.

## Product rules in the UI

- **The API owns every transition.** Render the project view and its `actions` flags. Do not re-implement domain rules in TypeScript, such as which question can be deferred, what is current, or what counts as reviewed.
- **Label fixture output** wherever it appears.
- **Leave unknowns visible.** An unknown cost or an absent rationale is displayed as unknown, never filled in.

## Styling

- Use Tailwind utilities and the theme tokens in `src/styles/index.css`. The color scheme follows the system. Use CSS Modules only where isolated custom styling is justified, as in `Markdown.module.css`.
- Use semantic elements first. Every control needs an accessible name. Manage focus when content is replaced; `App.test.tsx` covers focus on a new brief.

## Tests

- Vitest and Testing Library in jsdom. Build data with `src/test/factories.ts`. Mock the platform API at the `platform/` seam.
- Coverage floors: statements and lines 85%, functions 85%, branches 80%.
- Test what the user observes: roles, names, text, and focus. Do not test implementation details.
- Playwright journeys with axe live in `e2e/journeys.spec.ts` and run against the real API in fixture mode. A user-visible flow change gets a journey assertion.
