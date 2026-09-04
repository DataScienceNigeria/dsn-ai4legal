#!/usr/bin/env bash
# Bring the platform up for development.
#
# The infrastructure runs in containers and the two applications run on the
# host with reload, which is the only arrangement where a code change shows up
# without a rebuild. The API container stays down: it would hold port 8000
# against the host process, and the two serve different builds.
#
#   scripts/dev.sh            everything
#   scripts/dev.sh infra      containers only
#   scripts/dev.sh stop       stop the host processes, leave the containers
#
# Logs go to .dev/, one file per process.
#
# Each application is started with setsid and its three streams closed off the
# terminal. Backgrounding alone is not enough: a forked child inherits the
# shell's stdout, so `scripts/dev.sh | tee` sat there after everything was up,
# waiting on a pipe the worker's children were still holding open.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$ROOT/.dev"
API="$ROOT/apps/api"
WEB="$ROOT/apps/web"

# The ports come from .env, because ~/PORTS.md is the register for this machine
# and several projects here each wanted 3000, 8000 and 5432. Read one key at a
# time rather than sourcing the file: it holds secrets with characters a shell
# would try to interpret.
port_for() {
  local key="$1" fallback="$2" value
  value="$(sed -n "s/^${key}=//p" "$ROOT/.env" 2>/dev/null | tail -1 | tr -d '[:space:]')"
  echo "${value:-$fallback}"
}

API_PORT="$(port_for DSNLAI_API_PORT 8000)"
WEB_PORT="$(port_for DSNLAI_WEB_PORT 3004)"
export DSNLAI_WEB_PORT="$WEB_PORT"

# n8n is started with --no-deps because its compose dependency is the API
# container, which is deliberately not running here.
INFRA=(db redis minio mail opensign-mongo opensign opensign-client)

mkdir -p "$LOGS"

running() { pgrep -f "$1" >/dev/null 2>&1; }

wait_for() {
  local name="$1" url="$2" tries=60
  until curl -fsS -o /dev/null "$url" 2>/dev/null; do
    tries=$((tries - 1))
    if [ "$tries" -le 0 ]; then
      echo "  $name did not answer. See $LOGS." >&2
      return 1
    fi
    sleep 1
  done
  echo "  $name is up."
}

stop_host() {
  pkill -f "uvicorn app.main:app" 2>/dev/null || true
  pkill -f "celery -A app.worker.celery_app" 2>/dev/null || true
  pkill -f "next dev" 2>/dev/null || true
  echo "Host processes stopped. Containers are still running."
}

start_infra() {
  echo "Infrastructure:"
  (cd "$ROOT" && docker compose up -d "${INFRA[@]}" >/dev/null)
  (cd "$ROOT" && docker compose up -d --no-deps n8n >/dev/null)
  echo "  containers up."
}

start_api() {
  if running "uvicorn app.main:app"; then
    echo "  API already running."
    return
  fi
  (cd "$API" && ./.venv/bin/alembic upgrade head >"$LOGS/migrate.log" 2>&1)
  (cd "$API" && ./.venv/bin/python -m app.seed --if-empty >>"$LOGS/migrate.log" 2>&1)
  (cd "$API" && setsid ./.venv/bin/uvicorn app.main:app --reload \
     --host 0.0.0.0 --port "$API_PORT" </dev/null >"$LOGS/api.log" 2>&1 &)
  wait_for "API" "http://localhost:${API_PORT}/health"
}

start_worker() {
  if running "celery -A app.worker.celery_app"; then
    echo "  worker already running."
    return
  fi
  (cd "$API" && setsid ./.venv/bin/celery -A app.worker.celery_app worker \
     --beat --loglevel=info </dev/null >"$LOGS/worker.log" 2>&1 &)
  echo "  worker started."
}

start_web() {
  if running "next dev"; then
    echo "  web already running."
    return
  fi
  (cd "$WEB" && setsid npm run dev </dev/null >"$LOGS/web.log" 2>&1 &)
  wait_for "Web" "http://localhost:${WEB_PORT}/"
}

case "${1:-all}" in
  stop)
    stop_host
    ;;
  infra)
    start_infra
    ;;
  all)
    start_infra
    echo "Applications:"
    start_api
    start_worker
    start_web
    cat <<EOF

  Interface     http://localhost:${WEB_PORT}
  API docs      http://localhost:${API_PORT}/api/v1/docs
  Mail          http://localhost:$(port_for DSNLAI_MAIL_UI_PORT 8025)
  Object store  http://localhost:$(port_for DSNLAI_MINIO_CONSOLE_PORT 9101)
  Signing       http://localhost:$(port_for DSNLAI_OPENSIGN_CLIENT_PORT 3200)
  n8n           http://localhost:$(port_for DSNLAI_N8N_PORT 5678)

  Logs in .dev/. Stop the host processes with scripts/dev.sh stop.
EOF
    ;;
  *)
    echo "Usage: scripts/dev.sh [all|infra|stop]" >&2
    exit 1
    ;;
esac
