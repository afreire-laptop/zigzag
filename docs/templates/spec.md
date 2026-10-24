# <Change>

**Status:** Draft · **Updated:** YYYY-MM-DD · **Origin:** <PRD, finding, or request> · **Inventory:** <each area the change touches, as `existing: path:line` or `new`>

## Problem

<The current behavior, cited to code (path:line), and why it is wrong or insufficient.>

## Scope

<What changes, and what is explicitly not promised.>

## Design

<Numbered decisions: behavior, contracts (routes, Pydantic models, problem types), stored data and compatibility, the web client, and failure modes. Name the layer each change belongs to. Where a decision had a credible alternative, say why it lost.>

## Acceptance criteria

<Numbered, observable, and testable at the highest useful seam. Each names its test level: domain, application, HTTP harness, Vitest, Playwright, container smoke, or live evaluation.>

## Verification

<The tests to write first, and the commands to run: `pnpm check`, plus `pnpm contract`, `pnpm e2e`, or `pnpm docker:smoke` where the change needs them. Also the docs to update and the reviews required.>

## Likely affected files

<Paths. This is a forecast, not a constraint.>
