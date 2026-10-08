#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.local"
CDP_PORT=9222
CDP_URL="http://127.0.0.1:${CDP_PORT}/json/version"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This startup helper currently supports macOS only." >&2
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Copy .env.example to .env.local and configure the bridge CLI path first." >&2
  exit 1
fi

# .env.local is a trusted, machine-local configuration file maintained by the user.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

NODE_EXECUTABLE="${TRADINGVIEW_DESKTOP_BRIDGE_NODE:-node}"
BRIDGE_CLI="${TRADINGVIEW_DESKTOP_BRIDGE_CLI:-}"

if [[ -z "$BRIDGE_CLI" || ! -f "$BRIDGE_CLI" ]]; then
  echo "TRADINGVIEW_DESKTOP_BRIDGE_CLI must point to the local bridge src/cli/index.js in $ENV_FILE." >&2
  exit 1
fi
if ! command -v "$NODE_EXECUTABLE" >/dev/null 2>&1; then
  echo "Node.js was not found at '$NODE_EXECUTABLE'. Configure TRADINGVIEW_DESKTOP_BRIDGE_NODE in .env.local." >&2
  exit 1
fi

is_tradingview_cdp() {
  local response
  response="$(curl -fsS --max-time 2 "$CDP_URL" 2>/dev/null)" || return 1
  printf '%s' "$response" | "$NODE_EXECUTABLE" -e '
    let body = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => body += chunk);
    process.stdin.on("end", () => {
      try {
        const metadata = JSON.parse(body);
        process.exit(metadata["User-Agent"]?.includes("TradingView/") ? 0 : 1);
      } catch {
        process.exit(1);
      }
    });
  ' >/dev/null 2>&1
}

wait_for_cdp() {
  for _ in $(seq 1 60); do
    if is_tradingview_cdp; then
      return 0
    fi
    sleep 1
  done
  return 1
}

if is_tradingview_cdp; then
  echo "TradingView CDP is already available on port $CDP_PORT. Reusing the current session."
else
  OTHER_CDP="$(curl -fsS --max-time 2 "$CDP_URL" 2>/dev/null || true)"
  if [[ -n "$OTHER_CDP" ]]; then
    echo "Port $CDP_PORT is in use by a non-TradingView CDP service; refusing to attach to it." >&2
    exit 1
  fi

  if pgrep -x TradingView >/dev/null 2>&1; then
    echo "TradingView is open without the bridge port. Gracefully closing it before relaunch."
    osascript -e 'tell application "TradingView" to quit'
    for _ in $(seq 1 30); do
      if ! pgrep -x TradingView >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
    if pgrep -x TradingView >/dev/null 2>&1; then
      echo "TradingView did not quit gracefully. No force-close was attempted; close it manually and rerun." >&2
      exit 1
    fi
  fi

  if [[ -d "/Applications/TradingView.app" ]]; then
    TV_APP="/Applications/TradingView.app"
  elif [[ -d "$HOME/Applications/TradingView.app" ]]; then
    TV_APP="$HOME/Applications/TradingView.app"
  else
    echo "TradingView.app was not found in /Applications or ~/Applications." >&2
    exit 1
  fi

  echo "Opening TradingView with the bridge port $CDP_PORT enabled."
  open -na "$TV_APP" --args "--remote-debugging-port=$CDP_PORT"
  if ! wait_for_cdp; then
    echo "TradingView did not expose CDP at $CDP_URL within 60 seconds." >&2
    exit 1
  fi
fi

echo "Waiting for the TradingView bridge API to become ready..."
BRIDGE_READY=false
for _ in $(seq 1 60); do
  STATUS="$("$NODE_EXECUTABLE" "$BRIDGE_CLI" status 2>/dev/null || true)"
  if printf '%s' "$STATUS" | "$NODE_EXECUTABLE" -e '
    let body = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => body += chunk);
    process.stdin.on("end", () => {
      try {
        const status = JSON.parse(body);
        process.exit(status.success && status.cdp_connected && status.api_available ? 0 : 1);
      } catch {
        process.exit(1);
      }
    });
  ' >/dev/null 2>&1; then
    BRIDGE_READY=true
    break
  fi
  sleep 1
done

if [[ "$BRIDGE_READY" != true ]]; then
  echo "TradingView CDP is open, but the bridge API did not become ready within 60 seconds." >&2
  echo "Sign in to TradingView Desktop if prompted, wait for a chart to load, then rerun this script." >&2
  exit 1
fi
echo "TradingView bridge is ready."

EXPECTED_SYMBOLS="$(uv run --env-file "$ENV_FILE" python -c '
from god_market_api.global_market import RECORDED_WATCHLIST_GROUPS
for group in RECORDED_WATCHLIST_GROUPS:
    for instrument in group.instruments:
        print(instrument.symbol)
')"
WATCHLIST_JSON="$("$NODE_EXECUTABLE" "$BRIDGE_CLI" watchlist get)"
ACTUAL_SYMBOLS="$(printf '%s' "$WATCHLIST_JSON" | "$NODE_EXECUTABLE" -e '
  let body = "";
  process.stdin.setEncoding("utf8");
  process.stdin.on("data", chunk => body += chunk);
  process.stdin.on("end", () => {
    try {
      const result = JSON.parse(body);
      if (!result.success || !Array.isArray(result.symbols)) process.exit(2);
      process.stdout.write(result.symbols.map(item => String(item.symbol || "").trim().toUpperCase()).join("\n"));
    } catch {
      process.exit(2);
    }
  });
')" || true

if [[ "$ACTUAL_SYMBOLS" == "$EXPECTED_SYMBOLS" ]]; then
  echo "Active watchlist matches PS_Global_Indices (30 instruments)."
else
  echo "WARNING: The active TradingView watchlist is not the approved PS_Global_Indices list." >&2
  echo "The API can still start and use Official MCP, but Desktop fallback will be rejected until you select PS_Global_Indices in TradingView." >&2
fi

echo "Starting the local API at http://127.0.0.1:8000 (Ctrl+C to stop)."
cd "$ROOT_DIR"
exec uv run --env-file "$ENV_FILE" uvicorn god_market_api.app:app --reload --no-access-log
