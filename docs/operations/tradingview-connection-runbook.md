# TradingView connection runbook

## Healthy state

- TradingView Desktop is open and logged in.
- The local MCP bridge is available.
- The backend reports a recent successful chart-context update.
- The dashboard displays `Connected` with the source timestamp.

## If connection is unavailable

1. Do not act on stale setup results.
2. Confirm TradingView Desktop is open.
3. Confirm the MCP bridge and its local debugging/connection requirements are available.
4. Inspect the backend health view and logs for the failing component.
5. Refresh chart context only after the connection is restored.
6. Confirm a current timestamp before resuming evaluation.

## Safety rule

An unavailable, stale, or partially supported data source must never be represented as a current confirmed setup.
