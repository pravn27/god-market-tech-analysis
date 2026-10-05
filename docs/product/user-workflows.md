# User workflows

## Daily analysis workflow

1. Start TradingView Desktop and confirm its local MCP connection is healthy.
2. Start the local God Market service and open the localhost dashboard.
3. Review the connection state and last successful chart-context update.
4. Select a symbol and inspect Super TIDE through Ripple alignment.
5. Open setup details to examine passed, failed, pending, and unavailable rules.
6. Compare the result with the visible TradingView chart.
7. Record a manual decision; the system never submits an order.

## Near-ready setup workflow

1. A setup reaches its configured readiness threshold, such as 80%.
2. The dashboard records a state transition and shows an in-app notification.
3. If explicitly enabled, one Gmail message is sent for that transition.
4. The user validates the chart and chooses to watch, avoid, or treat the setup as confirmed.
5. Repeated notifications are suppressed until the setup changes state.

## Connection-loss workflow

1. The adapter detects TradingView Desktop, MCP, or source data is unavailable.
2. The dashboard presents `Data unavailable` or `Data stale`, with the last update time.
3. New evaluations pause; previous results are visibly labelled as stale.
4. When the connection recovers, the service refreshes context and records the recovery.
