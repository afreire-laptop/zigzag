#!/bin/sh
# Container smoke test of the committed tree, as a fresh machine would run it:
#   1. cp .env.example .env   2. docker compose up --build
# It runs in a disposable git worktree (your own .env and data are untouched), on its own compose project and
# port, then checks the stack, restarts and recreates it, and checks that the project survived.
#   SMOKE_PORT (default 18080)   SMOKE_E2E=1 also runs the Playwright journeys against the containers.
#   SMOKE_KEEP=1 leaves the stack running for inspection.
set -eu
repo="$(cd "$(dirname "$0")/.." && pwd)"
port="${SMOKE_PORT:-18080}"
project="intent-harness-smoke-$$"
work="$(mktemp -d "${TMPDIR:-/tmp}/intent-harness-smoke.XXXXXX")"
base="http://127.0.0.1:$port"

cleanup() {
  if [ "${SMOKE_KEEP:-0}" != "1" ]; then
    (cd "$work/tree" 2>/dev/null && docker compose -p "$project" down --volumes --remove-orphans >/dev/null 2>&1) || true
    git -C "$repo" worktree remove --force "$work/tree" >/dev/null 2>&1 || true
    rm -rf "$work"
  fi
}
trap cleanup EXIT INT TERM

git -C "$repo" worktree add --detach "$work/tree" HEAD >/dev/null
cd "$work/tree"
cp .env.example .env
export INTENT_WEB_PORT="$port"
docker compose -p "$project" up --build --detach --wait --wait-timeout 300

echo "== checks through $base"
project_id="$(python3 "$repo/scripts/smoke_check.py" "$base" create | tee /dev/stderr | tail -n 1)"

if [ "${SMOKE_E2E:-0}" = "1" ]; then
  echo "== browser journeys against the containers"
  (cd "$repo/apps/web" && E2E_BASE_URL="$base" pnpm exec playwright test)
fi

echo "== hardening"
sh "$repo/scripts/smoke_hardening.sh" "$project" "$port"

echo "== persistence"
docker compose -p "$project" restart api >/dev/null
python3 "$repo/scripts/smoke_check.py" "$base" verify "$project_id"
docker compose -p "$project" down >/dev/null
docker compose -p "$project" up --detach --wait --wait-timeout 120 >/dev/null
python3 "$repo/scripts/smoke_check.py" "$base" verify "$project_id"
echo "== container smoke test passed"
