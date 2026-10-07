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

Configure the bridge CLI path in the environment that starts the backend:

```bash
TRADINGVIEW_DESKTOP_BRIDGE_CLI="/path/to/tradingview-mcp/src/cli/index.js"
```

Node.js must be on `PATH`. Optionally set
`TRADINGVIEW_DESKTOP_BRIDGE_NODE` to the full Node.js executable path. The
TradingView Desktop app must be running with the local CDP port enabled. The
backend invokes only `watchlist get`; it does not switch the chart or edit the
watchlist.

## If connection is unavailable

1. Do not act on stale setup results.
2. Check the official MCP authentication and response state first.
3. If the primary source is unavailable, determine whether the approved Desktop fallback can provide the required context.
4. When fallback is used, confirm TradingView Desktop and its local debugging/connection requirements are available.
5. Inspect the backend health view and logs for the failing component.
6. Confirm a current timestamp and source ID before resuming evaluation.

## Safety rule

An unavailable, stale, or partially supported data source must never be represented as a current confirmed setup.
