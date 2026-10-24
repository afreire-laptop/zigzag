#!/bin/sh
# API development server with reload. Reads the repository's .env when present, as Docker Compose does.
set -eu
cd "$(dirname "$0")/.."
if [ -f ../../.env ]; then
  set -a
  . ../../.env
  set +a
fi
exec uv run --frozen uvicorn zigzag.main:create_app --factory --reload --reload-dir src \
  --host 127.0.0.1 --port 8000
