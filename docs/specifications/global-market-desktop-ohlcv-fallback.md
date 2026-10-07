# Specification: Global Market Desktop watchlist quote fallback

## Objective

When the official TradingView MCP cannot provide usable evidence for an
instrument in `PS_Global_Indices`, read that instrument's latest price and
displayed change percentage from the local TradingView Desktop watchlist. The
dashboard must identify the Desktop source and keep an item out of breadth when
the watchlist does not display a change percentage.

This improves evidence availability only. It does not generate a trading
recommendation, execute trades, change a TradingView chart, or change the
watchlist.

## Assumptions and constraints

- The official TradingView MCP remains the first source for every instrument.
- The Desktop bridge is attempted only after official OHLCV validation fails.
- The fallback must not change the active chart symbol, timeframe, layout,
  drawings, indicators, or watchlist.
- The official MCP remains first. Valid OHLC candles remain preferred for the
  dashboard's daily change calculation.
- The Desktop bridge's active-watchlist rows are accepted only when their
  ordered symbols exactly match the approved 30-symbol universe. The bridge
  does not expose a reliable watchlist name in this operation.
- A Desktop last price is shown if available. A direction is included in
  breadth only when a valid displayed change percentage is available.
- Every fallback result identifies `desktop_bridge` as its source. Its
  `source_timestamp` records local read time, not an exchange-provided quote
  timestamp; the warning makes this distinction visible.
- The existing bridge's `data_get_ohlcv` reads only the active chart.
  `quote_get(symbol)` does not load that symbol and must not be used for
  arbitrary-symbol lookup.

## Project commands

```bash
uv run pytest -q
uv run pytest -q tests/test_global_market_live.py
cd frontend && npm run lint && npm run typecheck && npm run build && npm test
```

## Project structure

- `src/god_market_api/providers.py` — source adapters and external-payload
  validation.
- `src/god_market_api/global_market.py` — Global Market orchestration and
  source-attributed instrument evidence.
- `tests/test_providers.py` — source adapter tests.
- `tests/test_global_market_live.py` — Global Market source/fallback tests.
- `docs/architecture/architecture-decisions/` — durable architecture choices.

## Interface contract

The existing `GET /api/v1/global-market-sentiment` endpoint remains backward
compatible. Source provenance is added, rather than replacing existing fields:

- official MCP success: source is `official_tradingview_mcp`;
- validated Desktop fallback success: source is `tradingview_desktop_bridge`;
- both sources unavailable: the item remains unavailable with an explanation
  that identifies which source attempts failed.

The Desktop adapter accepts an exchange-qualified symbol and timeframe and
returns normalized `ChartContext` data only when it can do so without a
TradingView mutation. It must reject any implementation that needs
`chart_set_symbol`, `chart_set_timeframe`, `pane_set_symbol`, or `batch_run`.

## Acceptance criteria

1. Official MCP is called first for every instrument.
2. Official OHLC is accepted when valid even if volume is null, because the
   Global Market calculation does not use volume.
3. An unavailable official result triggers one Desktop watchlist read for the
   snapshot, not a chart switch per instrument.
4. The fallback rejects the response unless the ordered symbols exactly match
   the approved `PS_Global_Indices` universe.
5. A price with no change percentage stays visible but remains unavailable for
   directional breadth.
6. API evidence identifies Desktop-sourced values and states that the timestamp
   is the local read time.
7. Tests cover null volume, official success (no fallback), Desktop fallback,
   missing change percentage, symbol-universe mismatch, and both sources
   unavailable.
8. Runtime validation confirms the Desktop bridge reads the current 30-symbol
   list without changing the active chart.

## Boundaries

- Always: validate third-party payloads, retain source attribution, run focused
  and full tests, and verify Desktop read-only behaviour before release.
- Ask first: extend the Desktop bridge protocol, add a dependency, change the
  public endpoint shape, or alter any TradingView UI state.
- Never: place orders, use broker APIs, silently switch a chart/pane, mutate a
  layout/watchlist, or treat invalid data as a market signal.

## Technical findings (2026-10-07)

Official MCP samples for affected index symbols returned complete OHLC values
with `v: null`. The backend previously called `float(null)`, converting a
valid OHLC candle into the invalid-candle error. The backend now treats volume
as optional.

The current Desktop bridge cannot safely request OHLCV for an arbitrary symbol
without switching a chart. Its `watchlist_get` operation can read visible rows
for the active watchlist. In the live check, those 30 ordered symbols matched
the approved universe, all 30 had a last price, and 13 had a displayed change
percentage. The quote fallback uses that read-only operation. See
`docs/validation/desktop-ohlcv-fallback-capability.md` for the capability record.
