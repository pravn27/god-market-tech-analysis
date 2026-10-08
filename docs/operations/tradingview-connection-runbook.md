# TradingView connection runbook

## Connection priority

1. Official TradingView MCP: primary source, authenticated through OAuth 2.1.
2. Existing local TradingView Desktop/CDP bridge: fallback only.

The dashboard must display the active source. A fallback is a visible operational event, not a hidden implementation detail.

Verified official-connector limits and supported read operations are recorded in the [capability matrix](../architecture/tradingview-mcp-capability-matrix.md).

## Healthy state

- The official TradingView MCP is authenticated and responds, **or** the fallback Desktop bridge is available.
- If fallback is active, TradingView Desktop is open and its local debugging connection is available.
- The backend reports a recent successful chart-context update and source ID.
- The dashboard displays `Connected` with the source timestamp.

## Desktop watchlist quote fallback

When the official MCP cannot provide a usable candle, the local backend may
read quote rows from the currently selected Desktop watchlist. The read is
accepted only when its ordered symbols exactly match the approved
`PS_Global_Indices` snapshot. The bridge's `watchlist_get` response does not
include a reliable list name or exchange timestamp; the dashboard marks these
values as Desktop-assisted and uses the local read time. If a row has no change
percentage, its displayed price is retained but the instrument is excluded
from breadth.

Configure the bridge CLI path in the ignored `.env.local` file (copy
`.env.example` once, then use the path appropriate for this machine):

```bash
TRADINGVIEW_DESKTOP_BRIDGE_CLI=/path/to/tradingview-mcp/src/cli/index.js
# Optional when Node.js is not available on PATH:
TRADINGVIEW_DESKTOP_BRIDGE_NODE=/path/to/node
```

On macOS, start the backend and prepare TradingView Desktop with:

```bash
./scripts/start-local.sh
```

The helper reuses a TradingView CDP session on port 9222 when available. If
TradingView is open without CDP, it requests a graceful quit and relaunches
TradingView with `--remote-debugging-port=9222`; it never force-kills the app.
It waits until the bridge status reports a connected chart API, then compares
the active watchlist's exact ordered symbols with the approved
`PS_Global_Indices` snapshot. It does not change which list is active or alter
watchlist contents. If another list is selected, startup continues with a
warning because Official MCP remains the primary source, but Desktop fallback
will be rejected until `PS_Global_Indices` is selected manually. The backend
invokes only the read-only `watchlist get` command.

The frontend remains separate. Start it in another terminal with
`cd frontend && npm run dev`. To stop the backend, press Ctrl+C in the
terminal running `start-local.sh`.

When Official MCP cannot provide evidence (such as an initialization error,
timeout, upstream handshake failure, or rate limit), the Global Market
request attempts the Desktop quote fallback once for that snapshot. It accepts
the response only if its ordered symbols exactly match the approved
`PS_Global_Indices` snapshot. Desktop values are source-labelled and use the
local observation time because the bridge does not provide per-quote
timestamps. If the row has a price but no daily change percentage, the price
may be shown while the instrument remains excluded from breadth. This fallback
does not provide historical candles and cannot replace OHLCV for technical
indicators or multi-timeframe analysis. If both sources fail, values remain
unavailable; do not present stale values as live.

## If connection is unavailable

1. Do not act on stale setup results.
2. Check Official MCP authentication and tool initialization; an authenticated token alone does not prove market-data tools are usable.
3. On 429 responses, avoid rapid retries and allow the request to use the Desktop fallback.
4. Check bridge health with `node <bridge>/src/cli/index.js status` and confirm CDP at `127.0.0.1:9222`.
5. Inspect the API result for `desktop_bridge` source attribution, local observation time, and per-instrument unavailable reasons.
6. Confirm the exact approved watchlist order and current source timestamp before resuming evaluation.

## Safety rule

An unavailable, stale, or partially supported data source must never be represented as a current confirmed setup.
