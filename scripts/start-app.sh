#!/usr/bin/env bash
# Start the whole local app in one terminal:
#   API       FastAPI (uvicorn --reload) on http://127.0.0.1:8000
#   Frontend  Vite dev server on http://localhost:5173
# Output from each process is prefixed with [api] or [web]. Ctrl+C stops both.
#
# Usage: ./scripts/start-app.sh [--skip-tv]
#   --skip-tv  skip the TradingView Desktop bridge preflight (no TradingView quit/relaunch)
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.local"
API_URL="http://127.0.0.1:8000"
WEB_URL="http://localhost:5173"
SKIP_TV=false

for arg in "$@"; do
  case "$arg" in
    --skip-tv) SKIP_TV=true ;;
    -h|--help)
      sed -n '2,8p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      exit 2
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This startup helper currently supports macOS only." >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Copy .env.example to .env.local and configure it first." >&2
  exit 1
fi
if [[ ! -x "$ROOT_DIR/frontend/node_modules/.bin/vite" ]]; then
  echo "Frontend dependencies are missing. Run: cd frontend && npm install" >&2
  exit 1
fi

port_in_use() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}
for port in 8000 5173; do
  if port_in_use "$port"; then
    echo "Port $port is already in use. Stop the process using it (or stop the earlier dev server) and rerun." >&2
    exit 1
  fi
done

# Preflight (TradingView bridge check, may relaunch TradingView) runs before anything is started.
if [[ "$SKIP_TV" == false ]]; then
  "$ROOT_DIR/scripts/start-local.sh" --preflight-only
else
  echo "Skipping the TradingView preflight (--skip-tv)."
fi

# Each background job gets its own process group so Ctrl+C can stop the whole process tree
# (uvicorn --reload and npm/vite both spawn children).
set -m
JOB_PIDS=()

stop_all() {
  trap - INT TERM EXIT
  for pid in ${JOB_PIDS[@]+"${JOB_PIDS[@]}"}; do
    kill -TERM -- "-$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap stop_all INT TERM EXIT

wait_for_url() {
  local url="$1" name="$2" attempt
  for attempt in $(seq 1 90); do
    if curl -fsS --max-time 2 -o /dev/null "$url" 2>/dev/null; then
      echo "$name is ready at $url"
      return 0
    fi
    sleep 1
  done
  echo "$name did not respond at $url within 90 seconds." >&2
  return 1
}

echo "Starting the API (http://127.0.0.1:8000)..."
(
  cd "$ROOT_DIR"
  exec uv run --env-file "$ENV_FILE" uvicorn god_market_api.app:app --reload --no-access-log
) > >(sed -u 's/^/[api] /') 2>&1 &
JOB_PIDS+=("$!")
wait_for_url "$API_URL/health" "API"

echo "Starting the frontend (http://localhost:5173)..."
(
  cd "$ROOT_DIR/frontend"
  exec npm run dev
) > >(sed -u 's/^/[web] /') 2>&1 &
JOB_PIDS+=("$!")
wait_for_url "$WEB_URL" "Frontend"

echo ""
echo "App is running:"
echo "  Frontend  $WEB_URL"
echo "  API docs  $API_URL/docs"
echo "Press Ctrl+C to stop both."
open "$WEB_URL" || true

wait
