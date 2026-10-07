#!/bin/sh
# Regenerates the OpenAPI contract and the TypeScript client from the API source, then fails if either differs
# from what is committed. Run after changing any Pydantic transport model or route.
set -eu
cd "$(dirname "$0")/.."
pnpm turbo run generate --force --output-logs=errors-only
paths="apps/api/openapi.json packages/api-client/src/generated"
if ! git diff --quiet -- $paths || [ -n "$(git ls-files --others --exclude-standard -- $paths)" ]; then
  echo "The generated contract is out of date. Run 'pnpm contract' and commit the result:" >&2
  git status --short -- $paths >&2
  exit 1
fi
echo "Contract and generated client match the API source."
