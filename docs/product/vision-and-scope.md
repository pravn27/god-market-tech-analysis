# Product vision and scope

## Vision

God Market Technical Analysis is a local, cross-platform decision-support dashboard for manual multi-timeframe technical analysis. It brings the user's TradingView Desktop chart context, defined trading rules, and setup monitoring into one explainable workspace.

## User outcome

For each configured symbol, the user can quickly understand:

1. the higher-timeframe market bias;
2. whether a trade setup is forming and why;
3. how many required conditions are satisfied;
4. whether an entry-timeframe trigger is still pending; and
5. why the system recommends `Trade`, `Watch`, `Avoid`, or `Data unavailable`.

## In scope

- Local browser dashboard served on the same machine.
- macOS and Windows support.
- TradingView Desktop context through the locally available MCP bridge.
- Multi-timeframe analysis: Monthly, Weekly, Daily, 4H, 1H, and 15m.
- Configurable manual trade setups with mandatory and weighted rules.
- Setup readiness, status history, connection health, and local notifications.
- Optional Gmail notification after explicit configuration and approval.

## Out of scope

- Broker integration, order placement, portfolio management, and automated or semi-automated trading.
- A public internet-facing service or multi-user hosted product.
- Treating the system output as financial advice.
- Assuming TradingView MCP is a guaranteed tick-by-tick market-data feed.

## Product principles

- The human makes the trading decision.
- Rules are transparent, versioned, and explainable.
- Missing or stale data results in caution, never a fabricated signal.
- The dashboard is a summary; the underlying checklist remains inspectable.
