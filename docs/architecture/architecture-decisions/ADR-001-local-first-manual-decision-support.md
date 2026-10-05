# ADR-001: Local-first manual decision support

## Status

Accepted for initial scope.

## Decision

Build the system as a local-only decision-support application. It will read available TradingView Desktop context through a local MCP bridge, evaluate documented manual setups, and present explanations. It will not connect to a broker or place orders.

## Consequences

- The user controls when the application and TradingView Desktop run.
- Local privacy and simple deployment are prioritised over multi-user access.
- Dashboard availability depends on the local machine and TradingView/MCP readiness.
- Later cloud or broker features require a new architecture decision and explicit scope change.
