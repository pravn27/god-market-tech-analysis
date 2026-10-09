# Specification: multi-timeframe analysis checklist

Status: **Approved 2026-10-09**. Decisions are recorded in [Decisions](#decisions).

## Objective

Give the user a one-screen, read-only **PAPA + SMM multi-timeframe checklist** for one instrument at a time. Instruments come from the user's TradingView watchlist `PS_DailyWatch_Favourite`; Nifty 50 (`NSE:NIFTY`) is the default selection. The page reproduces the layout of the user's own worksheet (`knowledge source/multi-timeframe-analysis.xlsx`, sheet `nifty50 latest`) and fills every row that can be calculated deterministically from TradingView OHLCV.

The user still owns the trade decision. Automated rows show the checklist wording used in the course notes, the raw values behind them, and the source/freshness of the candles. Subjective rows remain visible as **Manual check**.

### User stories

- As a trader, I open **Multi-Timeframe**, select Nifty 50, and see Super TIDE → RIPPLE evidence in the same row/column order as my worksheet.
- As a trader, I click any cell to see the raw indicator values, candle timestamps, and the exact rule that produced the label.
- As a trader, I see immediately when a timeframe is stale or unavailable, and the Double/Triple Screen decision is qualified rather than guessed.

## Knowledge sources

| Source (under `knowledge source/`) | Used for |
| --- | --- |
| `multi-timeframe-analysis.xlsx` → `nifty50 latest` | Layout, row order, label wording, layer/timeframe columns |
| `1 - SMM/SMM seminar key points.xlsx` → `All Indicators`, `Double Triple Screen`, `Time frames` | EMA, MACD, Stochastic, RSI rules; Double/Triple Screen tables; layer indicator roles |
| `1 - SMM/SMM Summary - Updated.xlsx` | Dow Theory definitions; indicator practical use; decision workflow |
| `1 - SMM/SMM DECISION SHEET.pdf` (scanned) | Tide/Wave signal definitions; "5 EMA PCO/NCO with 13 or 26 EMA in last 3 periods" |
| `2 - PAPA/PAPA Seminar key points.xlsx` → `BB Indicators Setups`, `Dow Theory Advanced`, `Candles Imp` | Bollinger Band states (UBBC/LBBC/BKT/BKP), DMI/ADX bands, advanced Dow price action, candle open/close rules |
| `2 - PAPA/PAPA Summary - Updated.xlsx` | Price action before indicators; ADX > 55–60 unsustainable; BB median bias |
| `GEO Panoramic Sessions/pdf notes/GEO P TRIPLE SCREEN.pdf`, `GEO P MOMENTUM.pdf`, `GEO P SWING.pdf` (scanned) | Ripple-level conditions (RSI, Stochastic, 5 EMA crossover, BB) used as supporting evidence |
| `Color codes.xlsx` | Indicator colours for any chart/legend in the UI |

GUE (Elliott wave) and FOME (options data) are out of scope for this feature.

## Layout contract

Eight timeframe columns in four layers, exactly as the worksheet. A timeframe that appears twice (4H, 1H) is fetched and calculated **once** and rendered in both columns.

| Layer | Column 1 | Column 2 | Screen indicator |
| --- | --- | --- | --- |
| Super TIDE | Monthly | Weekly | MACD |
| TIDE | Daily | 4H | MACD |
| WAVE | 4H | 1H | Stochastic / RSI |
| RIPPLE / Super RIPPLE | 1H | 15m | MACD |

### Rows

| # | Section | Row | Automated? |
| --- | --- | --- | --- |
| 1 | Overall Context / Dow Theory | Trend structure | Yes |
| 1 | | Where do you stand in overall trend / context? | Yes |
| 1 | | Support / resistance levels (horizontal) | Yes (nearest swing levels); angular trendlines manual |
| 1 | | Significant & event candles | Manual |
| 2 | Dow Theory Advanced + Price Action | Current candle open/close vs previous candle OHLC | Yes |
| 2 | | Special candles near support/resistance | Yes (candlestick patterns + location) |
| 3 | Indicators | Bollinger Band | Yes |
| 3 | | RSI | Yes |
| 3 | | DMI | Yes |
| 3 | | ADX | Yes |
| 3 | | MACD | Yes |
| 3 | | Stochastic | Yes |
| 3 | | EMAs | Yes |
| 4 | Double & Triple Screen decision | Per-layer screen signal (BUY / SELL, tick, PCO/NCO state) | Yes |
| 4 | | Double Screen decision, Triple Screen decision | Yes |
| 4 | | What's your interpretation? | Manual |
| 5 | Concepts / Setups / Chart patterns | Concept / chart pattern | Manual |
| 5 | | Weapon / confirmation candle, volume of weapon candle | Manual |
| 5 | | Momentum or swing setup | Manual |
| 5 | | Follow-up candles; what-if analysis | Manual |

## Calculation profile `mtf-checklist-v1`

All values are calculated locally from the normalized candles of each timeframe. The **latest candle is used even if still forming**; the response labels it `live_candle: true` until the candle's last NSE session closes (15:30 IST): the same day for Daily, Friday for Weekly, the last weekday of the month for Monthly, and the earlier of the period end or 15:30 for intraday candles. NSE holidays are not modelled.

| Indicator | Settings |
| --- | --- |
| EMA | 5, 13, 26, 50, 100, 150, 200 (seeded with SMA, TradingView-compatible) |
| RSI | 14, Wilder smoothing |
| MACD | 12 / 26 / 9 (EMA) |
| Bollinger Bands | 20-period SMA basis, 2 standard deviations (population) |
| DMI / ADX | 14, Wilder smoothing |
| Stochastic | %K 14, %K smoothing 3, %D 3 |
| ATR | 14, Wilder (only for proximity tests) |
| Swing pivots | 5 candles on each side |

### Configurable thresholds (defaults)

| Name | Default | Meaning |
| --- | ---: | --- |
| `recent_crossover_periods` | 3 | A PCO/NCO counts as current if it occurred within the last 3 candles (SMM decision sheet wording). |
| `slope_lookback` | 3 | Rising/falling, expanding/contracting compare with the value 3 candles earlier. |
| `rsi_near_50_band` | 45–55 | "Near 50". |
| `bb_near_median_fraction` | 0.10 | Price within 10% of band width from the basis is "near median". |
| `bb_flat_tolerance` | 0.5% | Band movement below this percentage over `slope_lookback` is "flat". |
| `sr_proximity_atr` | 1.0 | Price within 1 ATR of a swing level is "near" it. |
| `macd_near_zero_fraction` | 0.10 | MACD within 10% of its recent 50-candle absolute range is "near zero line". |
| `dmi_contracting_lookback` | 3 | `abs(+DI − −DI)` lower than 3 candles earlier is "contracting". |

Insufficient candles for any setting produce an **unavailable** cell with a reason; they never produce a neutral label.

## Rule mapping

Each automated cell produces: `labels[]` (worksheet wording), `bias` (`bullish | bearish | neutral | unavailable`), `values{}` (raw numbers), and `rule_ids[]`.

### 1. Dow Theory trend (SMM Summary; PAPA Dow Theory Advanced)

Using the last two confirmed swing highs and lows:

| Condition | Label | Bias |
| --- | --- | --- |
| Higher high and higher low | `HH - HL (Up Trend)` | bullish |
| Lower low and lower high | `LL - LH (Down Trend)` | bearish |
| Otherwise | `HLs - LHs (Sideways Trend)` | neutral |

Fewer than two swing highs and two swing lows → unavailable.

### 1. Where do you stand / support–resistance

- Swing levels = all confirmed swing highs and lows. Support = nearest level at or below the latest close; resistance = nearest level above it. A broken level therefore changes role (resistance turning into support, the PAPA "impact line").
- `Near Support` / `Near Resistance` when within `sr_proximity_atr × ATR` (the closer one wins if both).
- No level above → `Above prior resistance`; no level below → `Below prior support`; otherwise `Mid-range`.
- Values include both levels, their candle timestamps, and the distance in ATR and percent.

### 2. Advanced Dow + price action (PAPA Dow Theory Advanced; Candles Imp)

Compare the latest candle (C) with the previous candle (P):

| Condition | Label |
| --- | --- |
| P bearish, C.close > P.close | `Close > Prev. Bearish Close` (confirmation) |
| P bearish, C.close > P.open | `Close > Prev. Bearish Open` (continuation) |
| C.close > P.high | `Close > Prev. Candle High` (bullish reversal confirmation) |
| P bullish, C.close < P.close | `Close < Prev. Bullish Close` |
| P bullish, C.close < P.open | `Close < Prev. Bullish Open` |
| C.close < P.low | `Close < Prev. Candle Low` (bearish reversal confirmation) |
| C.open > P.high / C.open > P.close | `Gap up` / `Bullish Open (above Prev. Close)` |
| C.open < P.low / C.open < P.close | `Gap down` / `Bearish Open (below Prev. Close)` |
| Open = low / close = high (within 2% of the candle range) | `Strong Bullish Open (Open = Low)` / `Strong Bullish Close (Close = High)` (and bearish equivalents) |

All matching labels are listed. Bias: close beyond the previous high/low decides; otherwise close vs previous close; equal → neutral.

### 2. Special candles (SMM Summary; PAPA Candles Imp)

Detected on the latest two/three candles: Bullish/Bearish Engulf, Bullish/Bearish Piercing, Hammer, Inverted Hammer, Hanging Man, Doji, Spinning Top, Morning Star, Evening Star, Mother candle (latest candle inside the previous candle's range). The label adds `in Support` / `at Resistance` when the location rule above says near. No pattern → `No special candle`, bias neutral.

### 3. Bollinger Band (PAPA BB Indicators Setups)

| Condition | Label | Bias |
| --- | --- | --- |
| High ≥ upper band and upper band expanding | `UBBC, BB Expands` | bullish |
| Low ≤ lower band and lower band expanding | `LBBC, BB Expands` | bearish |
| Upper band touched within `recent_crossover_periods`, band flat | `UBBC Failure, BKT` | bearish |
| Lower band touched within `recent_crossover_periods`, band flat | `LBBC Failure, BKP` | bullish |
| Otherwise | `Price is Above Median` / `Price is Below Median` / `Price is Near Median` | bullish / bearish / neutral |

Append `Bands are Flat` or `Bands Expanding` / `Bands Contracting`. Values: upper, basis, lower, band width, %B.

### 3. RSI (SMM All Indicators; PAPA)

| Condition | Label | Bias |
| --- | --- | --- |
| > 80 | `> 80, Unsustainable for Bulls` | bullish (caution) |
| > 60 | `> 60, Bullish Momentum` | bullish |
| within 45–55 | `Near 50` | neutral |
| 40–60 otherwise | `Swing zone (40 - 60)`, plus `Above 50` / `Below 50` | neutral |
| < 40 | `< 40, Bearish Momentum` | bearish |
| < 20 | `< 20, Unsustainable for Bears` | bearish (caution) |

Add `Crossing above 60` / `Crossing below 40` / `Crossing above 40` / `Crossing below 60` when it happened within `recent_crossover_periods`.

### 3. DMI (PAPA)

`+DI > -DI` (bullish) or `-DI > +DI` (bearish), plus `Contracting` / `Expanding` from the DI spread, plus `PCO` / `NCO` when +DI crossed −DI within `recent_crossover_periods`.

### 3. ADX (PAPA BB Indicators Setups)

| ADX | Label |
| --- | --- |
| < 10 | `No Momentum (< 10)` |
| 10–12 | `Momentum Building (10 - 12)` |
| 12–14 | `Good Momentum (12 - 14)` |
| > 14 | `Excellent Momentum (> 14)` |
| > 55 | `Unsustainable (> 55)` |

Prefixed with `Raising` / `Falling` (compared with `slope_lookback`), e.g. `Raising > 12 or 15 (Gaining good strength in Trend)` / `Falling (Losing strength in Trend)` as in the worksheet. ADX is non-directional; bias follows DMI only when ADX is rising and ≥ 12, otherwise neutral.

### 3. MACD (SMM All Indicators)

- State: `PCO` when MACD > signal, `NCO` when MACD < signal.
- Tick: `Up Tick` when MACD rose vs previous candle, `Down Tick` when it fell, `Flat` otherwise.
- Position: `above Zero Line`, `below Zero Line`, `near Zero Line`.
- Signal (worksheet wording): `Buy Signal` when PCO or up tick; `Sell Signal` when NCO or down tick; `(PCO)` / `(NCO)` prefix when the crossover happened within `recent_crossover_periods`. Example: `(NCO) Sell Signal above Zero Line`.
- Bias = bullish for PCO + Up Tick, bearish for NCO + Down Tick, otherwise neutral (`Not Clear`).

### 3. Stochastic (SMM All Indicators)

- Zone: `> 80 Overbought`, `< 20 Oversold`, otherwise `Neutral zone`.
- `PCO Buy Signal` when %K crossed above %D within `recent_crossover_periods`; `NCO Sell Signal` when crossed below.
- Wording examples: `(< 20) Buy Signal from OverSold (10 - 20)`, `(> 80) NCO Sell Signal from OverBought (80 - 90)`, `(Near 80) PCO Buy Signal Up tick`.
- No recent crossover and neutral zone → `Not Clear`, neutral.

### 3. EMAs (SMM All Indicators; Summary)

- Price relation for each of 5, 13, 26, 50 (and 100/150/200 where available): `Price > 5`, `Price < 50`, …
- Stack: `POC, 5 > 13 > 26` / `NOC, 5 < 13 < 26`; long stack `POC, 100 > 150 > 200` / `NOC, 100 < 150 < 200`.
- Crossover: `5 EMA PCO with 13 / 26 EMA` or `NCO` within the last 3 periods (SMM decision sheet).
- Bias: bullish if price > 50 EMA and 5 > 13 > 26; bearish if price < 50 EMA and 5 < 13 < 26; otherwise neutral (`EMAs intermingled`).

### 4. Screen signals and decisions (SMM Double / Triple Screen)

Per timeframe screen signal:

| Layer | Indicator | BUY | SELL |
| --- | --- | --- | --- |
| Super TIDE, TIDE, RIPPLE | MACD | Up Tick, or flat after a down move (SMM decision sheet: "TI Uptick OR Flat after Down") | Down Tick, or flat after an up move |
| WAVE | Stochastic / RSI | %K up tick or recent PCO, and RSI not < 40 | %K down tick or recent NCO, and RSI not > 60 |

Each signal cell shows `BUY` / `SELL` / `NOT CLEAR`, `Up Tick` / `Down Tick`, and `PCO state` / `NCO state`, matching the worksheet.

Layer signal = the two timeframe signals when they agree; otherwise `NOT CLEAR`.

**Double Screen decision (Tide + Wave)** from the SMM table:

| Tide | Wave | Decision |
| --- | --- | --- |
| BUY | BUY | `BUY` |
| BUY | SELL | `No Buy — wait for Wave to align with Tide` |
| SELL | SELL | `SELL` |
| SELL | BUY | `No Sell — wait for Wave to align with Tide` |
| any NOT CLEAR | | `NOT CLEAR` |

Computed for three pairs: Super TIDE + TIDE (strategic), TIDE + WAVE (primary, shown as the headline), WAVE + RIPPLE.

**Triple Screen decision (Tide + Wave + Ripple)** from the SMM table:

The SMM sheet holds two tables: an **entry** table (rows 26–28) and a **position-management** table for a position already held in the Tide direction (rows 31–33). Each combination therefore yields an entry decision and, where the sheet defines one, a position note.

| Tide | Wave | Ripple | Entry decision | Position note |
| --- | --- | --- | --- | --- |
| BUY | BUY | BUY | `BUY — go for refined entry` | `Stay Bullish` |
| BUY | SELL | BUY | `No Buy — wait for WAVE to align with TIDE` | — |
| BUY | BUY | SELL | `No Buy — wait for RIPPLE to align with TIDE / WAVE` | `Carefully bullish — keep an eye on WAVE` |
| BUY | SELL | SELL | `No Buy — wait for WAVE to align with TIDE` | `Exit in WAVE / refined exit in RIPPLE` |
| SELL | … | … | Mirrored wording (`No Sell …`, `SELL — go for refined entry`) | Mirrored (`Stay Bearish`, `Carefully bearish …`) |
| any NOT CLEAR | | | `NOT CLEAR` | — |

Double Screen wording uses the pair's layer names, e.g. `No Buy — wait for TIDE to align with Super TIDE` for the strategic pair.

If a required timeframe is unavailable or stale, the decision is `INCOMPLETE` with the missing timeframe named.

Every decision displays the caption: *Checklist signal derived from the SMM Double/Triple Screen rules — not financial advice.*

## API

`GET /api/v1/mtf-analysis/{symbol}?refresh_mode=prefer_cache|force_refresh`

```text
MultiTimeframeAnalysis
  symbol, display_name, requested_at, profile_version ("mtf-checklist-v1")
  completeness: complete | partial | unavailable
  timeframes{monthly..15m}: source, source_timestamp, freshness_state, live_candle, last_close, unavailable_reason
  layers[4]: name, timeframes[2], screen_indicator, signal
  rows[]: id, section, label, automated
    cells{timeframe}: labels[], bias, values{}, rule_ids[], unavailable_reason
  decisions: double_screen[3], triple_screen
  warnings[]
```

- Reuses the existing multi-timeframe orchestrator, cache, freshness policy, and request guardrails. Existing `/api/v1/chart-context` and `/api/v1/multi-timeframe-context` contracts are unchanged.
- Only symbols in the recorded `PS_DailyWatch_Favourite` snapshot are accepted. Others return 422.
- `GET /api/v1/mtf-analysis/instruments` returns the snapshot: sections in watchlist order, each with its symbols, plus `default_symbol` (`NSE:NIFTY`) and the snapshot's `recorded_at`.

### Instrument snapshot

- The watchlist is read **once, read-only**, through the TradingView Desktop page's own custom-list endpoint (`GET /api/v1/symbols_list/custom/`), which does not change the active watchlist, chart, or layout.
- The snapshot is stored in the repository (`src/god_market_api/data/ps_dailywatch_favourite.json`) with section names, symbol order, and `recorded_at`. Section markers (`###…`) become section names with invisible characters removed.
- `scripts/sync-mtf-watchlist.mjs` re-reads the list on request and rewrites the snapshot; it never writes to TradingView.
- Market data for every instrument still comes from the official MCP through the existing orchestrator.

Snapshot recorded 2026-10-09 (32 instruments):

| Section | Symbols |
| --- | --- |
| LONG / MEDIUM TERM INVESTMENT | NSE:NIFTYBEES, NSE:GOLDBEES, NSE:SILVERBEES |
| F & O | NSE:NIFTY, NSE:BANKNIFTY, NSE:INDIAVIX |
| DAILY_WATCHLIST 2024 JAN | NSE:PNB, NSE:BANKINDIA, NSE:IDFCFIRSTB, NSE:RADICO, NSE:SOBHA, NSE:OBEROIRLTY, NSE:LT, NSE:HDFCBANK, NSE:LUPIN, NSE:RELIANCE, NSE:LTM, NSE:DIVISLAB, NSE:HCG, NSE:HINDZINC, NSE:AXISBANK, NSE:BHARTIARTL, NSE:TATAPOWER, NSE:MCX |
| STOCKS WATCHLIST | NSE:RVNL, NSE:RAILTEL, NSE:NTPC, NSE:PFC, NSE:GAIL, NSE:GRSE, NSE:POWERGRID, NSE:RECLTD |

## UI

- New primary navigation item **Multi-Timeframe** at `/multi-timeframe`, next to **Global Market**; same header, theme switcher, and footer.
- Controls: searchable instrument dropdown grouped by the `PS_DailyWatch_Favourite` sections (default Nifty 50), last-updated time, Refresh. The selected symbol is kept in the URL (`?symbol=NSE:NIFTY`).
- Headline strip: Double Screen (Tide + Wave) and Triple Screen decisions with the disclaimer.
- Matrix: sticky checklist column; grouped column headers per layer with timeframe sub-columns; each cell shows compact tags coloured by bias (bullish green, bearish red, neutral grey, unavailable dashed); manual rows show a muted `Manual check` tag.
- Per-timeframe header shows source, freshness badge, and `Live candle`.
- Clicking a cell opens a drawer with raw values, rule wording, and candle timestamps.
- Responsive: horizontal scroll for the matrix on narrow screens; keyboard focusable cells; light/dark theme via existing tokens.

## Commands

```text
Backend tests:   uv run pytest -q
Backend focused: uv run pytest -q tests/test_technical_indicators.py
Frontend:        cd frontend && npm run lint && npm run typecheck && npm test -- --run && npm run build
Local run:       ./scripts/start-local.sh  (backend)  ·  cd frontend && npm run dev
```

## Project structure

```text
src/god_market_api/technical_indicators.py   pure indicator series
src/god_market_api/price_structure.py        pivots, Dow trend, S/R, candle patterns, price action
src/god_market_api/mtf_checklist.py          profile, thresholds, rule mapping
src/god_market_api/mtf_screens.py            screen signals, layers, Double/Triple Screen decisions
src/god_market_api/mtf_analysis.py           use case over the orchestrator
tests/test_technical_indicators.py, test_price_structure.py, test_mtf_checklist.py, test_mtf_analysis_api.py
frontend/src/features/multi-timeframe/       page, matrix, drawer, hooks, tests
```

## Testing strategy

- Pure functions tested with fixed OHLCV fixtures and independently computed expected values (tolerance 1e-6), plus edge cases: empty, short, flat (zero range), non-finite.
- Rule tests: one test per label table row above.
- Screen decision tests: every row of the Double/Triple Screen tables plus the incomplete case.
- API tests with fixture providers only; no network.
- Frontend component tests for matrix rendering, manual rows, unavailable timeframe, drawer content, and navigation.
- Live read-only check: Nifty 50 Daily and 1H indicator values compared with the TradingView chart (tolerance: EMA/BB 0.1%, RSI/ADX/Stochastic ±1 point).

### Live validation (2026-10-09, read-only)

The active TradingView chart was `NSE:RELIANCE` Daily, so that chart was used instead of Nifty 50 (changing the chart symbol or timeframe is not allowed). Values were read from the chart's own studies; the official technicals endpoint returned HTTP 429 at the time.

| Indicator (chart settings) | TradingView | Calculated | Result |
| --- | --- | --- | --- |
| RSI 14 | 35.416 | 35.42 | Match |
| MACD 12/26/9 (line / signal / histogram) | −26.7999 / −25.1277 / −1.6723 | −26.7999 / −25.1277 / −1.6723 | Match |
| Stochastic 14/3/3 (%K / %D) | 26.750 / 38.628 | 26.75 / 38.63 | Match |
| DMI 14/14 (+DI / −DI / ADX) | 13.624 / 37.759 / 39.886 | 13.62 / 37.76 / 39.89 | Match |
| Bollinger 20/2 (upper / basis / lower) | 1278.35 / 1217.14 / 1155.93 | 1278.85 / 1217.64 / 1156.43 | Within 0.1% (0.04%) |

The Bollinger difference comes only from the basis: the user's chart uses an **EMA** basis, the profile uses the standard SMA basis; the band width (122.42) is identical. EMAs are validated indirectly through MACD. 1H was not compared because the chart timeframe could not be changed; the same functions and data source are used for every timeframe.

## Boundaries

- **Always:** read-only TradingView access; show source and freshness; treat unavailable data explicitly; keep thresholds in the versioned profile; run focused and full tests before each commit.
- **Ask first:** adding symbols outside the watchlist snapshot; adding new dependencies (no new Python/JS dependency is planned); changing existing API contracts; enabling heuristic chart-pattern detection.
- **Never:** place orders or present output as a trade instruction; modify TradingView charts, watchlists, or layouts; log OAuth tokens; fabricate values for missing candles.

## Success criteria

1. `/multi-timeframe` shows all 8 columns and every worksheet row for Nifty 50 in one screen (with horizontal scroll on narrow viewports).
2. Every automated cell shows worksheet wording, bias colour, and drill-down values; every manual row is visibly manual.
3. Indicator values match TradingView within the tolerances above for Daily and 1H.
4. The same candles and profile always produce the same labels and decisions.
5. A missing or stale timeframe makes affected cells unavailable and the dependent decision `INCOMPLETE`.
6. Backend and frontend suites, lint, typecheck, and build pass.

## Decisions

Confirmed by the user on 2026-10-09:

| Topic | Decision |
| --- | --- |
| Symbols | All instruments in `PS_DailyWatch_Favourite`, grouped by section; Nifty 50 (`NSE:NIFTY`) by default |
| Watchlist access | One-time read-only snapshot stored in the app; refreshed on request by a script |
| Subjective rows | Shown as `Manual check`, not automated |
| Wording | Worksheet wording (BUY / SELL / NOT CLEAR, Up Tick, PCO state) with a not-advice caption |
| Columns | Eight columns in four layers, as in the worksheet |
| Candle | Latest candle even if forming, labelled live |
| Thresholds | Defaults above, configurable in the profile |

## Open questions

- Indices (`NSE:NIFTY`, `NSE:BANKNIFTY`, `NSE:INDIAVIX`) have no volume on TradingView; volume evidence is shown only when candles carry volume.
- `NSE:INDIAVIX` is a volatility index; the checklist is calculated the same way but its bias colours do not mean market direction. The UI shows a note for it.
- Angular trendlines and chart patterns are manual in v1; heuristic detection may be proposed later as a separate, approved change.
