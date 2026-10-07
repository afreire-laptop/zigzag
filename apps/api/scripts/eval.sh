#!/bin/sh
# Live evaluation runner. Reads the repository's .env when present, as scripts/dev.sh does, but variables already set in
# the shell take precedence, so `INTENT_MODEL=<slug> pnpm eval ...` evaluates another model without editing .env.
set -eu
cd "$(dirname "$0")/.."
if [ -f ../../.env ]; then
  exec uv run --frozen --env-file ../../.env python -m evals.run "$@"
fi
exec uv run --frozen python -m evals.run "$@"
