# Multi-timeframe analysis checklist — task checklist

Plan: [mtf-plan.md](mtf-plan.md) · Spec: [mtf-analysis-checklist.md](../docs/specifications/mtf-analysis-checklist.md)

## Task 0: Specification and plan

- [x] Knowledge source reviewed (worksheet, SMM, PAPA, decision sheets, GEO Panoramic setups, colour codes).
- [x] User decisions recorded (symbol, manual rows, wording, columns, live candle, thresholds).
- [x] User approves the spec and plan (2026-10-09).
- [x] `PS_DailyWatch_Favourite` read once, read-only (32 instruments, 4 sections) and recorded in the spec.

## Task 1: Indicator engine

- [x] EMA, RSI, MACD, Bollinger, DMI/ADX, Stochastic, ATR match fixtures.
- [x] Insufficient or invalid data returns typed unavailable results.
- [x] `uv run pytest -q tests/test_technical_indicators.py` and full suite pass.

## Task 2: Price structure and price action

- [x] Pivots, Dow trend, support/resistance, candle-vs-previous, candlestick patterns tested.
- [x] `uv run pytest -q tests/test_price_structure.py` and full suite pass.

## Checkpoint A: calculations

- [x] Tasks 1–2 complete; full backend suite passes (108 tests).

## Task 3: Checklist rule mapping

- [x] Profile `mtf-checklist-v1` with configurable thresholds.
- [x] Every rule-table row in the spec has a test.
- [x] `uv run pytest -q tests/test_mtf_checklist.py` and full suite pass.

## Task 4: Screen signals and decisions

- [x] Layer signals, Double Screen (3 pairs), Triple Screen, INCOMPLETE handling tested.
- [x] Full suite passes (171 tests).

## Checkpoint B: rules review

- [x] User approves sample output wording and decisions (2026-10-09).

## Task 5: Analysis use case and API

- [x] `GET /api/v1/mtf-analysis/{symbol}` returns complete/partial/unavailable; symbol outside the snapshot → 422.
- [x] `GET /api/v1/mtf-analysis/instruments` returns the watchlist sections in order; snapshot JSON and read-only sync script added.
- [x] Existing endpoints unchanged; full suite passes (182 tests).

## Task 6: Multi-Timeframe page

- [x] Nav item and `/multi-timeframe` route.
- [x] 8-column grouped matrix, decision strip, manual rows, drawer, timeframe status.
- [x] Frontend lint, typecheck, tests (17), build pass; browser check done against live Nifty 50 and Reliance data.

## Checkpoint C: page review

- [x] User approves the page (2026-10-09); live-candle badge switched to NSE session hours.

## Task 7: Live read-only validation

- [x] Daily values compared with the TradingView chart and recorded in the spec (chart was on NSE:RELIANCE Daily; RSI, MACD, Stochastic, DMI/ADX match; Bollinger within 0.04% because the chart uses an EMA basis). 1H not compared: the chart timeframe may not be changed.
- [x] Roadmap updated.
