#!/bin/sh
# Checks the documentation and the agent workflow files, then tests, lints, and type-checks the workflow scripts
# and the Claude Code hook. Part of `pnpm check`, so CI runs it too. Needs git, python3, and `uv sync` for apps/api.
set -eu
cd "$(dirname "$0")/.."
python3 scripts/check_docs.py
python3 -W error -m unittest discover -s scripts/tests -t scripts
uv run --frozen --project apps/api ruff check --config scripts/ruff.toml scripts .claude/hooks
uv run --frozen --project apps/api ruff format --check --config scripts/ruff.toml scripts .claude/hooks
pnpm --filter @zigzag/api exec pyright -p ../../scripts/pyrightconfig.json
