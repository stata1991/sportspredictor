#!/usr/bin/env bash
# Run Alembic migrations against the database specified by DATABASE_URL.
# Usage:  ./scripts/migrate.sh          — upgrade to head
#         ./scripts/migrate.sh downgrade -1  — roll back one revision
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

if [ -z "${DATABASE_URL:-}" ]; then
  echo "ERROR: DATABASE_URL is not set" >&2
  exit 1
fi

ACTION="${1:-upgrade}"
TARGET="${2:-head}"

echo "Running: alembic $ACTION $TARGET"
alembic "$ACTION" "$TARGET"
