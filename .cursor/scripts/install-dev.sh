#!/usr/bin/env bash
# Idempotent Cloud Agent / local bootstrap for goo_school (Aria Edu).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

install_apt_if_missing() {
  local pkg="$1"
  dpkg -s "$pkg" >/dev/null 2>&1
}

need_apt=0
for pkg in python3.12-venv python3-dev libpq-dev postgresql postgresql-contrib redis-server build-essential; do
  if ! install_apt_if_missing "$pkg"; then
    need_apt=1
    break
  fi
done

if [[ "$need_apt" -eq 1 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
      python3.12-venv python3-dev libpq-dev \
      postgresql postgresql-contrib redis-server build-essential
  else
    echo "Missing system packages and sudo is unavailable." >&2
    exit 1
  fi
fi

if [[ ! -d "$ROOT/venv" ]]; then
  python3 -m venv "$ROOT/venv"
fi

"$ROOT/venv/bin/pip" install --upgrade pip -q
"$ROOT/venv/bin/pip" install -r "$ROOT/requirements.txt" -q

mkdir -p "$ROOT/logs"

if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
fi

# PostgreSQL: database `aria` (matches .env.example / settings defaults)
if command -v pg_isready >/dev/null 2>&1; then
  if command -v sudo >/dev/null 2>&1; then
    sudo service postgresql start 2>/dev/null || true
  fi
  if pg_isready -h localhost -q 2>/dev/null; then
    if command -v sudo >/dev/null 2>&1; then
      sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='aria'" | grep -q 1 \
        || sudo -u postgres psql -c "CREATE DATABASE aria;"
      sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'Ludvanne';" 2>/dev/null || true
    fi
  fi
fi

echo "install-dev.sh: venv, Python deps, .env, and DB bootstrap complete."
