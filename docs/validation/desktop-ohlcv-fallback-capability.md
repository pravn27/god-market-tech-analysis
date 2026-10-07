# Desktop watchlist quote fallback capability check

- Date: 2026-10-07
- Scope: read-only source inspection and bridge readiness check
- Outcome: current bridge cannot provide arbitrary-symbol OHLCV safely; its
  visible watchlist quotes can support a constrained quote-only fallback

## Findings

1. The TradingView Desktop CDP endpoint at `127.0.0.1:9222` was initially not
   reachable. After the user-approved TradingView restart with CDP enabled, the
   bridge became available; the active chart was `NSEIX:NIFTY1!` on daily and
   the read-only watchlist check did not change it.
2. The bridge's `data_get_ohlcv` / `tv ohlcv` command reads OHLCV from the
   active chart's main series. It has no symbol or timeframe argument.
3. The `quote_get(symbol)` command accepts an optional symbol string, but its
   implementation reads OHLCV from the active chart's main series and assigns
   the supplied symbol string to the returned `symbol` field. It does not load
   or verify that symbol. This means it must not be used to retrieve or label
   per-watchlist fallback data.
4. The bridge's `batch_run` can request OHLCV across symbols/timeframes, but it
   calls `setSymbol` and `setResolution` on the active chart before reading the
   bars. This changes user-visible TradingView state and is outside the
   approved read-only fallback scope.
5. The bridge's `watchlist_get` reads quote text (`last`, `change`, and
   `change_percent`) from rows displayed in the currently selected watchlist
   panel. It does not return historical candles or verify that the selected
   list is `PS_Global_Indices`; virtualized/off-screen rows may also be absent.
6. After TradingView was relaunched with CDP enabled, the active watchlist read
   returned the same 30 symbols in the same order as the approved
   `PS_Global_Indices` snapshot. It included a last price for all 30 symbols
   and a displayed percentage change for 13 symbols. The read did not change
   the active chart (`NSEIX:NIFTY1!`, daily).
7. Direct official-MCP OHLCV reads for `TVC:DJI`, `TVC:VIX`, `TVC:HSI`, and
   `TVC:CAC40` returned valid `t/o/h/l/c` values but `v: null`. The backend's
   candle normalizer attempted `float(null)` and rejected those candles.
8. The local API's OAuth status reported `connected` and discovered 35 tools.
   One live dashboard snapshot briefly received rejected market-data responses
   for two symbols and used Desktop-assisted quotes for those rows. Direct
   official-MCP retries returned valid OHLCV for both symbols; the dashboard's
   next refresh used official data for all 30 rows. The rejected responses
   were transient in this check; their upstream cause was not exposed in the
   MCP result, so they are not attributed to OAuth failure.
9. The authenticated tool inventory names OHLCV and technical-rating tools
   `mcp-tv-get-ohlcv` and `mcp-tv-get-technicals-rating`. The adapter had been
   calling short aliases, which produced an MCP client warning; it now calls
   the advertised names. The exact OHLCV tool returned valid bars in a
   read-only verification. A later pre-commit session check found CDP
   unavailable, so Desktop fallback readiness is not claimed for that latest
   check; the API returns an explicit fallback-unavailable warning instead.

## Decision

The current bridge does not meet the symbol-addressable, non-mutating OHLCV
capability gate. It does support a constrained read-only quote fallback through
visible watchlist rows when the ordered symbols match the approved universe.

The quote fallback cannot provide an exchange quote timestamp or candles.
Symbols without a displayed daily percentage retain their last price but stay
excluded from breadth.

No TradingView chart, pane, layout, watchlist, or indicator was changed during
this check. Direct official-MCP probes confirmed valid OHLC fields for the
affected indices with `v: null`, which is accepted as optional volume by the
backend.

## Evidence paths

- Bridge implementation: `src/core/data.js` (`getOhlcv`, `getQuote`)
- Bridge batch implementation: `src/core/batch.js` (`batchRun`)
- Bridge tools: `src/tools/data.js`
- Bridge CLI: `src/cli/commands/data.js`

## Next decision

The selected approach is the visible-watchlist quote fallback. Runtime
configuration and source-attributed behavior are implemented in the local API.
