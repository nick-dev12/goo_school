#!/usr/bin/env bash
# Start PostgreSQL and Redis for local / Cloud Agent development.
set -euo pipefail

start_service() {
  local name="$1"
  if command -v sudo >/dev/null 2>&1; then
    sudo service "$name" start 2>/dev/null || true
  fi
}

start_service postgresql
start_service redis-server

if ! redis-cli ping >/dev/null 2>&1; then
  redis-server --daemonize yes 2>/dev/null || true
fi

for _ in $(seq 1 30); do
  if pg_isready -h localhost -q 2>/dev/null && redis-cli ping >/dev/null 2>&1; then
    echo "PostgreSQL and Redis are ready."
    exit 0
  fi
  sleep 1
done

echo "Timed out waiting for PostgreSQL or Redis." >&2
exit 1
