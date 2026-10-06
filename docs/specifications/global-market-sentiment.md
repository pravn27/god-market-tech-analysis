# Specification: Global Market Sentiment dashboard

## Product outcome

Provide a local dashboard that summarizes the source-attributed performance and breadth of the TradingView Desktop watchlist named `PS_Global_Indices`. It should make it easy to scan regional market context before a manual analysis session.

The dashboard is market context only. It does not issue a trading instruction, choose a trade setup, place an order, or silently alter the TradingView watchlist.

## Architecture and source policy

```text
React + Ant Design dashboard
        ↓ local HTTP only
FastAPI Global Market use case
        ↓
Official TradingView MCP: price/OHLCV facts (primary)
TradingView Desktop bridge: PS_Global_Indices discovery and layout context (approved fallback/read-only companion)
```

- `PS_Global_Indices` is the authoritative initial universe and its existing section names/order must be preserved.
- `PS ASTA Setup - black theme` is the visual reference for the dashboard's Ant Design dark token theme. The dashboard does not modify the TradingView layout.
- The official MCP remains the primary price-data source. The Desktop bridge must never become a hidden price-data fallback.
- A missing Desktop bridge or unavailable watchlist produces a clear unavailable state; it must not be replaced with an invented symbol list.
- Any proposed addition, deletion, or reorder in `PS_Global_Indices` is a dry-run proposal requiring the user's exact confirmation before mutation.

## First-release dashboard behaviour

1. Load the current watchlist snapshot and group instruments by its existing sections.
2. Show a source timestamp, freshness/completeness state, and per-item warning whenever data is partial or unavailable.
3. Display an evidence-only breadth summary: advancing, declining, unchanged, and unavailable items for a selected timeframe.
4. Support a Daily default view with card/table presentation and region/section filtering.
5. Show loading, empty, error, and partial-data states explicitly.
6. Do not calculate a recommendation, readiness score, or setup conclusion.

## Stable local API contract

`GET /api/v1/global-market-sentiment?timeframe=daily`

The response will contain:

- watchlist identity and read timestamp;
- `complete`, `partial`, or `unavailable` aggregate state;
- ordered groups that mirror watchlist sections;
- source-attributed instrument performance evidence and per-item availability;
- aggregate breadth counts and an explanation of excluded/unavailable entries;
- warnings that make source limitations visible.

The existing raw chart-context and MTF endpoints remain unchanged.

## Acceptance criteria

1. The UI renders fixture-backed, grouped market evidence in the Ant Design dark theme.
2. The local API preserves watchlist group order and source/freshness evidence.
3. An unavailable or partial source never appears as neutral, positive, or confirmed sentiment.
4. All watchlist modifications require a separate dry-run proposal and user confirmation.
5. The React UI communicates only with the local FastAPI API; it never calls TradingView MCP directly.
