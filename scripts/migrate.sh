#!/usr/bin/env bash
# Run Alembic migrations for the football schema.
#
# Usage:
#   ./scripts/migrate.sh up      — upgrade to head
#   ./scripts/migrate.sh sql     — print SQL without running (dry-run)
#   ./scripts/migrate.sh status  — show current revision
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_ROOT"

# Load DATABASE_URL from backend/.env if not already in environment.
if [ -z "${DATABASE_URL:-}" ]; then
  if [ -f backend/.env ]; then
    DATABASE_URL="$(grep -m1 '^DATABASE_URL=' backend/.env | cut -d= -f2-)"
    export DATABASE_URL
  fi
  if [ -z "${DATABASE_URL:-}" ]; then
    echo "ERROR: DATABASE_URL is not set (checked env and backend/.env)" >&2
    exit 1
  fi
fi

ALEMBIC="alembic -c backend/shared/alembic.ini"

case "${1:-up}" in
  up)
    echo "Running: alembic upgrade head"
    $ALEMBIC upgrade head
    ;;
  sql)
    echo "-- SQL that would be executed by 'upgrade head':"
    $ALEMBIC upgrade head --sql
    ;;
  status)
    $ALEMBIC current
    ;;
  *)
    echo "Usage: $0 {up|sql|status}" >&2
    exit 1
    ;;
esac
