# ADR-002: Official TradingView MCP primary, Desktop bridge fallback

## Status

Accepted for the initial connection design.

## Context

Two TradingView integration paths are available:

1. The official TradingView MCP service at `https://mcp.tradingview.com/mcp`, authenticated through OAuth 2.1.
2. An existing local TradingView Desktop/CDP bridge that requires TradingView Desktop to run with its local debugging connection available.

## Decision

Use the official TradingView MCP as the primary connector. Use the existing Desktop bridge only as a backup when the official MCP is unavailable or does not provide a required, validated capability.

## Rules

- The adapter normalizes both paths into the same internal `ChartContext` contract.
- A source change is explicit, logged, and shown to the user; it is never silent.
- If neither path can supply fresh required data, the system reports `Data unavailable` rather than reusing stale data as current.
- Both sources must be tested independently before automatic fallback is enabled.
- The fallback path does not modify TradingView watchlists, layouts, drawings, indicators, or scripts.

## Consequences

- The system can remain useful during a temporary outage or capability gap in one connector.
- The adapter and tests must cover source-specific differences, authentication, rate limits, freshness, and error handling.
- TradingView Desktop is optional for the normal official-MCP path but required whenever the fallback is active.
