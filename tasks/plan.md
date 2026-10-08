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

- [x] Backend/API/frontend tests pass and frontend build succeeds.
- [x] A fixture-backed Daily view works end-to-end locally.
- [x] Human reviews the dashboard information hierarchy and source-status presentation.

### Phase 3: Live source and usability

- [x] Task 6: Connect the approved read-only watchlist and official-MCP price source, with bounded requests and source-attributed partial results.
- [x] Task 7: Add section filters, table/card choice, and a detail drawer without changing watchlist data.
- [ ] Task 8: Produce a `PS_Global_Indices` coverage dry-run; request confirmation before any proposed add/delete/reorder action.

### Checkpoint: feature complete

- [x] Tests, lint, type checks, and production build pass.
- [x] One local live read-only dashboard check is recorded.
- [x] No credentials are exposed and no TradingView watchlist/layout was modified without the user's exact confirmation.

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

---

# Implementation Plan: Global Market Desktop watchlist quote fallback

## Overview

Accept null official-MCP volume when the OHLC fields are valid, then use a
source-labelled, read-only Desktop watchlist quote only when official evidence
is unavailable. The official MCP remains primary.

## Architecture decisions

- The fallback is per instrument and runs only after official MCP validation
  fails.
- The existing Desktop bridge cannot read arbitrary-symbol candles without
  switching a chart, so the fallback reads the currently selected watchlist.
- The watchlist is accepted only when its exact ordered symbol list matches the
  approved `PS_Global_Indices` snapshot.
- A Desktop quote without a displayed change percentage retains its price but
  stays unavailable for directional breadth.

## Dependency graph

```text
Official payload validation and Desktop visible-watchlist quote proof
        │
        ├── Optional-volume handling in official candle normalization
        │        │
        │        └── Desktop watchlist reader + normalization tests
        │                 │
        │                 └── Global Market official-first fallback orchestration
        │
        └── source-labelled API/UI evidence
```

## Task list

### Phase 4: Capability gate

- [x] Task 9: Prove or reject a symbol-addressable, non-mutating Desktop OHLCV
  capability for two daily candles.

  - Acceptance: No call changes the active chart symbol, timeframe, pane,
    layout, or watchlist; the proof records the exact bridge capability and its
    response shape.
  - Verify: Run the TradingView session pre-flight and a read-only capability
    check; compare active chart state before and after.
  - Dependency: Approved fallback specification.
  - Scope: Small; validation/bridge documentation only.

### Checkpoint: capability decision

- [x] Arbitrary-symbol candles remain unavailable without changing chart state.
- [x] Visible watchlist read returns the approved 30-symbol sequence and is
  documented in `docs/validation/desktop-ohlcv-fallback-capability.md`.

### Phase 5: Safe fallback vertical slice

- [x] Task 10: Add a normalized Desktop watchlist quote reader and contract
  tests.

  - Acceptance: It validates the exact approved ordered universe, parses last
    price/change percent, and invokes only the read-only `watchlist get` CLI.
  - Verify: `uv run pytest -q tests/test_desktop_bridge.py`.
  - Dependency: Task 9 capability proof.
  - Scope: Medium; provider module and tests.

- [x] Task 11: Add official-first fallback orchestration to Global Market and
  surface the selected source in local API/dashboard evidence.

  - Acceptance: Official success bypasses Desktop; official failure attempts
    one watchlist read; missing change percentages stay out of breadth.
  - Verify: `uv run pytest -q tests/test_global_market_live.py`, frontend
    lint/typecheck/build/test commands, and a local source-label visual check.
  - Dependency: Task 10.
  - Scope: Medium; orchestration, API types/UI evidence, and tests.

### Checkpoint: complete

- [x] Full backend suite passes.
- [x] Live read-only Desktop fallback was verified when the approved
  30-symbol list was active; the bridge does not switch watchlists.
- [x] Each fallback item identifies Desktop-assisted evidence and the local
  observation time.

## Risks and mitigations

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Desktop bridge only exposes active-chart candles | High | Use visible watchlist rows; never switch the chart. |
| Active watchlist differs from the approved universe | High | Reject the entire Desktop snapshot unless symbol order matches exactly. |
| A row lacks a change percentage | Medium | Retain price, but exclude the item from directional breadth. |
| Desktop is closed or CDP is unavailable | Medium | Keep official data primary and return typed unavailable evidence. |
| Source provenance is hidden | High | Contract and UI test source label for every fallback result. |

## Open question

The bridge does not expose quote timestamps or watchlist identity through its
read operation. The fallback therefore requires an exact ordered symbol match
and labels its observation time as the local read time.

### Phase 6: Local runtime enablement

- [x] Task 12: Configure a local-only bridge path and make the supported backend
  startup command load it.

  - Acceptance: The bridge CLI path is stored in an ignored local environment
    file, never hard-coded into tracked application code; the example and
    runbook explain setup on each machine.
  - Verify: Existing bridge and fallback regression tests pass with the
    environment file loaded; confirm the API can invoke the configured CLI.
  - Dependency: Task 11 and a healthy read-only Desktop bridge.
  - Scope: Medium; example config, ignored local config, and startup docs.

- [x] Task 13: Restart the local API with fallback configuration and verify
  failover through the Global Market endpoint.

  - Acceptance: When Official MCP evidence is unavailable, the endpoint returns
    any Desktop-readable prices as `desktop_bridge` with a local observation
    time; missing change percentages remain excluded from breadth.
  - Verify: Check `/health`, `/api/v1/global-market-sentiment`, bridge health,
    source labels, the exact 30-symbol order, and that the active chart remains
    unchanged.
  - Dependency: Task 12.
  - Scope: Small; local runtime verification and delivery evidence only.

### Checkpoint: runtime fallback enabled

- [x] Local config remains ignored and contains no credentials.
- [x] Focused and full backend tests pass.
- [x] Live API demonstrates Official-first, Desktop-assisted fallback while
  retaining explicit unavailable evidence where quote fields are missing.
- [x] Backend startup and shutdown are controlled by the documented command.

- [x] Task 14: Add a safe macOS startup helper for TradingView bridge readiness.

  - Acceptance: One command reuses TradingView if CDP port 9222 is ready, or
    gracefully relaunches it with CDP enabled; it waits for bridge readiness,
    validates the active watchlist, then launches the API.
  - Safety: Never force-kill TradingView or silently switch/edit the active
    watchlist. Warn clearly when the active symbols do not match the approved
    `PS_Global_Indices` snapshot.
  - Verify: Shell syntax, backend tests, and live API fallback with the exact
    approved watchlist active. The relaunch branch remains a recovery path and
    is not exercised when a healthy CDP session already exists.
  - Dependency: Task 13.
  - Scope: Small; local startup helper and operational documentation.
