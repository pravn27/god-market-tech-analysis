# Implementation Plan: Global Market Sentiment UI

## Overview

Build the first user-facing, local-only React dashboard for global market context. It will render the existing `PS_Global_Indices` TradingView watchlist with source-attributed performance and breadth evidence through the FastAPI backend. The presentation follows the useful interaction patterns of the reference Global Markets page while using its own Ant Design dark theme and never reusing its yfinance implementation.

## Architecture decisions

- Use React, TypeScript, Vite, Ant Design, TanStack Query, React Router, Zustand, and ECharts only where a chart materially improves comprehension.
- Keep the React application in a new `frontend/` directory. It calls FastAPI over localhost only and has no TradingView credentials or MCP access.
- Use `PS_Global_Indices` only after a read-only Desktop MCP inspection succeeds. Existing watchlist sections and ordering are data, not UI configuration to rewrite.
- Use the official MCP as the primary price/OHLCV source. Desktop bridge support is explicit and source-labelled.
- Start with Daily performance/breadth. Multi-timeframe display follows after the daily vertical slice is verified.
- Use an additive `/api/v1/global-market-sentiment` contract; do not change raw E-03 endpoints.

## Dependency graph

```text
Desktop bridge readiness + read-only watchlist snapshot
        │
        ├── Global-market API contract and fixture data
        │        │
        │        ├── Backend watchlist/snapshot use case
        │        │        │
        │        │        └── Local API endpoint
        │        │                 │
        │        │                 └── React API client and query state
        │        │                          │
        │        │                          └── Ant Design dashboard vertical slice
        │        │
        └── Coverage dry-run and user-confirmed watchlist changes (separate)
```

## Task list

### Phase 1: Source proof and contract

- [x] Task 1: Verify Desktop bridge readiness and capture a read-only `PS_Global_Indices`/layout snapshot. No watchlist or layout mutation.
- [x] Task 2: Define typed Global Market Sentiment response contracts, availability semantics, and fixture watchlist data.

### Checkpoint: source and contract

- [x] Desktop/watchlist availability is known and recorded.
- [x] Fixture-backed contract preserves group order and unavailable evidence.
- [x] Human reviews the response shape before live dashboard integration.

### Phase 2: Daily vertical slice

- [x] Task 3: Implement the fixture-backed backend global-market snapshot use case and additive local API endpoint.
- [x] Task 4: Scaffold the TypeScript React/Vite application with the `PS ASTA Setup` Ant Design dark token theme.
- [x] Task 5: Implement the Daily Global Market dashboard: summary, group/table display, refresh, loading, empty, error, and partial states.

### Checkpoint: daily dashboard

- [ ] Backend/API/frontend tests pass and frontend build succeeds.
- [ ] A fixture-backed Daily view works end-to-end locally.
- [ ] Human reviews the dashboard information hierarchy and source-status presentation.

### Phase 3: Live source and usability

- [x] Task 6: Connect the approved read-only watchlist and official-MCP price source, with bounded requests and source-attributed partial results.
- [x] Task 7: Add section filters, table/card choice, and a detail drawer without changing watchlist data.
- [ ] Task 8: Produce a `PS_Global_Indices` coverage dry-run; request confirmation before any proposed add/delete/reorder action.

### Checkpoint: feature complete

- [ ] Tests, lint, type checks, and production build pass.
- [ ] One local live read-only dashboard check is recorded.
- [ ] No credentials are exposed and no TradingView watchlist/layout was modified without the user's exact confirmation.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Desktop bridge unavailable | High | Surface as a prerequisite failure; do not create a replacement watchlist. |
| Official MCP rate limits many index requests | High | Use a bounded backend request policy, cache source context, and return partial evidence. |
| Watchlist symbol mapping ambiguity | Medium | Preserve existing symbols; mark new mappings `review`; never invent exchange prefixes. |
| UI treats unavailable data as neutral | High | Typed availability and explicit visual status; exclude unavailable items from breadth with explanation. |
| Reference UI semantics leak yfinance assumptions | Medium | Reuse only user-facing layout patterns, not its data model or calculations. |

## Open questions

- Desktop MCP is currently not running. Task 1 must establish the actual `PS_Global_Indices` section structure before live integration.
- Whether the initial sentiment display should include non-index proxies such as VIX, DXY, yields, commodities, or India ADRs is deferred to the coverage dry-run and requires explicit user confirmation for additions.
- E-04 technical enrichment stays planned separately; it is not part of the first Global Market daily dashboard slice.
