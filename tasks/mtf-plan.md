# Implementation Plan: Multi-timeframe analysis checklist (Nifty 50)

Governing specification: [mtf-analysis-checklist.md](../docs/specifications/mtf-analysis-checklist.md).

## Overview

Fill the user's PAPA + SMM multi-timeframe worksheet automatically for Nifty 50 from TradingView OHLCV, and present it on a new **Multi-Timeframe** page. This plan absorbs E-04 Tasks 1–4 (indicator and price-structure evidence) and adds a versioned checklist interpretation, an additive API, and the UI.

## Architecture decisions

- Pure calculation modules (no I/O): `technical_indicators.py`, `price_structure.py`, `mtf_checklist.py`.
- One use case (`mtf_analysis.py`) composes the existing E-03 orchestrator with the pure modules; 4H and 1H are calculated once and referenced by two layers.
- No new dependencies: indicators are implemented in plain Python over the candle list (≤ 500 candles × 6 timeframes).
- Additive endpoint `GET /api/v1/mtf-analysis/{symbol}`; existing endpoints unchanged.
- Frontend feature folder `features/multi-timeframe/` reuses the theme, header, and React Query patterns from Global Market.

## Dependency graph

```text
Spec (Task 0)
  └── Indicator engine (Task 1) ─┐
  └── Price structure (Task 2) ──┼── Checklist rules (Task 3) ── Screen decisions (Task 4)
                                 │                                      │
                                 └──────────── API use case + endpoint (Task 5)
                                                        │
                                                UI page + nav (Task 6)
                                                        │
                                            Live validation (Task 7)
```

Tasks 1 and 2 are independent; everything else is sequential.

## Tasks

### Task 1 — Indicator engine

EMA (5/13/26/50/100/150/200), RSI 14, MACD 12/26/9, Bollinger 20/2, DMI/ADX 14, Stochastic 14/3/3, ATR 14 as full series with explicit insufficient-data results.

- Acceptance: fixture values match independently computed expectations; short/empty/flat/non-finite inputs return typed unavailable results.
- Verify: `uv run pytest -q tests/test_technical_indicators.py`; full suite.
- Files: `src/god_market_api/technical_indicators.py`, `tests/test_technical_indicators.py`, `tests/fixtures/ohlcv_*.py`.

### Task 2 — Price structure and price action

Swing pivots (5/5), Dow trend, nearest support/resistance with ATR distance, latest-vs-previous candle price action, candlestick patterns.

- Acceptance: every label table row in the spec has a passing test; no pattern → explicit "No special candle".
- Verify: `uv run pytest -q tests/test_price_structure.py`; full suite.
- Files: `src/god_market_api/price_structure.py`, `tests/test_price_structure.py`.

### Checkpoint A — calculations

- [ ] Tasks 1–2 complete; full backend suite passes.

### Task 3 — Checklist rule mapping

Versioned profile `mtf-checklist-v1` with thresholds; per-timeframe cells for every automated row (labels, bias, values, rule ids); manual rows.

- Acceptance: one test per rule-table row (BB, RSI, DMI, ADX, MACD, Stochastic, EMAs, Dow, location, price action, special candles).
- Verify: `uv run pytest -q tests/test_mtf_checklist.py`; full suite.
- Files: `src/god_market_api/mtf_checklist.py`, `src/god_market_api/models.py`, `tests/test_mtf_checklist.py`.

### Task 4 — Screen signals and decisions

Per-timeframe screen signal by layer indicator; layer signal; three Double Screen pairs; Triple Screen; `INCOMPLETE` handling.

- Acceptance: every row of the SMM Double/Triple Screen tables plus mirror and incomplete cases tested.
- Verify: `uv run pytest -q tests/test_mtf_checklist.py`; full suite.
- Files: `src/god_market_api/mtf_checklist.py`, `tests/test_mtf_checklist.py`.

### Checkpoint B — rules review

- [ ] User reviews sample output (fixture-based JSON) for wording and decisions before API/UI work.

### Task 5 — Analysis use case and API

`mtf_analysis.py` over the orchestrator; `GET /api/v1/mtf-analysis/{symbol}` restricted to the `PS_DailyWatch_Favourite` snapshot, `refresh_mode`, completeness, warnings; `GET /api/v1/mtf-analysis/instruments`; snapshot JSON and read-only `scripts/sync-mtf-watchlist.mjs`.

- Acceptance: fixture-provider tests for complete, partial (15m missing), unavailable, symbol outside the snapshot (422), instruments endpoint order; existing endpoint tests unchanged.
- Verify: `uv run pytest -q tests/test_mtf_analysis_api.py`; full suite; inspect OpenAPI.
- Files: `src/god_market_api/mtf_analysis.py`, `src/god_market_api/data/ps_dailywatch_favourite.json`, `scripts/sync-mtf-watchlist.mjs`, `src/god_market_api/app.py`, `tests/test_mtf_analysis_api.py`.

### Task 6 — Multi-Timeframe page

Header nav item, route, API client types, query hook, instrument dropdown, decision strip, 8-column grouped matrix, bias tags, manual rows, timeframe status headers, evidence drawer, light/dark styling.

- Acceptance: component tests for nav, matrix structure (4 layers × 2 columns), manual rows, unavailable timeframe, drawer; browser check against the live backend.
- Verify: `cd frontend && npm run lint && npm run typecheck && npm test -- --run && npm run build`.
- Files: `frontend/src/App.tsx`, `frontend/src/api/client.ts`, `frontend/src/features/multi-timeframe/*`, `frontend/src/styles.css`.

### Checkpoint C — page review

- [ ] User reviews the page layout and wording in the browser.

### Task 7 — Live read-only validation

Compare Nifty 50 Daily and 1H values (EMA, BB, RSI, MACD, ADX/DMI, Stochastic) with the TradingView chart; record results and limitations.

- Acceptance: values within spec tolerances or deviations explained; no chart/watchlist mutation; no OAuth data recorded.
- Verify: full suites; local request.
- Files: `docs/validation/mtf-analysis-live-validation-<date>.md`, `docs/product/delivery-roadmap.md`.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Indicator values differ from TradingView (seeding/smoothing) | Use TradingView-compatible seeding (SMA seed for EMA, Wilder for RSI/ATR/DMI); validate live in Task 7 |
| Monthly history shorter than 200 candles | EMA 150/200 cells become unavailable with a reason; other rows unaffected |
| Live candle makes labels change intraday | Labelled `Live candle`; refresh timestamp shown |
| Official MCP rate limit on 6 × 500-candle fetch | Existing cache, coalescing, and concurrency guardrails; prefer_cache default |
| Swing pivot detection mislabels trend on noisy 15m | Pivot window configurable; drawer shows the pivots used |
