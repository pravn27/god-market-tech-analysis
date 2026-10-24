# Specification: multi-timeframe analysis checklist

Status: **Approved 2026-10-09**. Decisions are recorded in [Decisions](#decisions).

## Objective

Give the user a one-screen, read-only **PAPA + SMM multi-timeframe checklist** for one instrument at a time. Instruments come from the user's TradingView watchlist `PS_Commodity`; NATGAS (`PEPPERSTONE:NATGAS`) is the default selection. The page reproduces the layout of the user's own worksheet (`knowledge source/multi-timeframe-analysis.xlsx`, sheet `nifty50 latest`) and fills every row that can be calculated deterministically from TradingView OHLCV.

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
| 1 | | Dow structure v2 (closed candles) | Yes (additive; see [Dow Structure v2](dow-structure-v2.md)) |
| 1 | | Where do you stand in overall trend / context? | Yes |
| 1 | | Support / resistance levels (horizontal) | Yes (nearest swing levels); angular trendlines manual |
| 1 | | Significant & event candles | Manual |
| 2 | Dow Theory Advanced + Price Action + Candlestick Pattern | Current candle open/close vs previous candle OHLC | Yes |
| 2 | | Heikin-Ashi candle | Yes (own row, neutral bias) |
| 2 | | Candlestick pattern | Yes |
| 2 | | Special candles near support/resistance | Yes (location only, neutral bias) |
| 3 | Indicators | Bollinger Band | Yes |
| 3 | | RSI | Yes |
| 3 | | DMI | Yes |
| 3 | | ADX | Yes |
| 3 | | MACD | Yes |
| 3 | | Stochastic | Yes |
| 3 | | EMAs | Yes |
| 3 | | Divergence (RSI, MACD, Stochastic %K) | Yes (own row, directly after EMAs) |
| 4 | Double & Triple Screen decision | Per-layer screen signal (BUY / SELL, tick, PCO/NCO state) | Yes |
| 4 | | Double Screen decision, Triple Screen decision | Yes |
| 4 | | What's your interpretation? | Manual |
| 5 | Concepts / Setups / Chart patterns | Concept / chart pattern | Yes for Double Top / Double Bottom; other concepts manual |
| 5 | | Weapon / confirmation candle | Manual |
| 5 | | Volume of weapon candle | Yes (latest closed candle vs 20-candle average) |
| 5 | | Momentum or swing setup | Manual |
| 5 | | Follow-up candles; what-if analysis | Manual |

## Calculation profile `mtf-checklist-v1`

All values are calculated locally from the normalized candles of each timeframe. The **latest candle is used even if still forming**; the response labels it `live_candle: true` until the candle's exchange session closes. Session close (IST): NSE 15:30, MCX 23:30 (its 23:55 US-DST schedule is not modelled). Exchanges not listed (PEPPERSTONE, TVC, CAPITALCOM) trade around the clock, so their candles are live until the period ends. Intraday candles end at the earlier of the period end and the session close; Weekly ends on Friday's close, Monthly on the last weekday's close. Holidays are not modelled.

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

The compatibility Dow row uses the latest candle as before. The additive
`dow_structure_v2` row excludes the latest candle when it is still forming,
normalizes confirmed pivots into alternating swings, distinguishes contracting
and expanding ranges, and reports structure-break evidence. It does not affect
Double/Triple Screen decisions.

### Configurable thresholds (defaults)

| Name | Default | Meaning |
| --- | ---: | --- |
| `recent_crossover_periods` | 3 | A PCO/NCO counts as current if it occurred within the last 3 candles (SMM decision sheet wording). |
| `slope_lookback` | 3 | Rising/falling, expanding/contracting compare with the value 3 candles earlier. |
| `rsi_near_50_band` | 45–55 | "Near 50". |
| `bb_near_median_fraction` | 0.10 | Price within 10% of band width from the basis is "near median". |
| `bb_flat_tolerance` | 0.5% | Band movement below this percentage over `slope_lookback` is "flat". |
| `ema_flat_tolerance` | 0.5% | EMA 5/13/26/50 movement at or below this percentage over `slope_lookback` is "flat". |
| `ema_steep_tolerance` | 1.5% | EMA 5/13/26/50 movement at or above this percentage over `slope_lookback` (in the stack's direction) is "steep". |
| `sr_proximity_atr` | 1.0 | Price within 1 ATR of a swing level is "near" it. |
| `macd_near_zero_fraction` | 0.10 | MACD within 10% of its recent 50-candle absolute range is "near zero line". |
| `dmi_contracting_lookback` | 3 | `abs(+DI − −DI)` lower than 3 candles earlier is "contracting". |
| `dow_significance_atr` | 0.5 | V2 reports whether both compared swing changes are at least 0.5 ATR; this does not alter structure or bias. |
| `divergence_lookback` | 40 | The later of the last two confirmed price pivots must be within 40 closed candles for a divergence label. |
| `divergence_confirm_bars` | 2 | A swing counts for divergence once 2 closed candles follow it (the Dow pivots still use 5). |
| `volume_average_period` | 20 | Volume average taken over the 20 closed candles before the latest closed candle. |
| `volume_near_average_band` | 0.2 | Volume ratio within ±20% of the average is "Average volume". |
| `volume_double_ratio` | 2.0 | Volume ratio at or above 2.0 is "Double average volume (high)". |
| `fib_tolerance` | 0.03 | A retracement within 3 percentage points of 23.6 / 38.2 / 50 / 61.8 / 78.6% also names that level. |
| `pattern_lookback` | 60 | Double top / bottom pivots must fall within the last 60 closed candles. |
| `double_top_tolerance` | 0.015 | Two peaks (or troughs) within 1.5% of each other, with the neckline at least 1.5% away from them. |
| `double_top_min_gap` | 10 | Two peaks (or troughs) must be at least 10 candles apart. |

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
- **Breakout / breakdown** (label on the `support_resistance` row, bias unchanged): the latest closed candle's close crosses a confirmed swing high (`Breakout above <level>`) or swing low (`Breakdown below <level>`), with the prior close on the other side. A volume note follows: `volume confirms` when the volume ratio is at least 1 + `volume_near_average_band`, otherwise `volume does not confirm`; the note is omitted when volume is unavailable.
- **Fibonacci zone** (label on the `location` row, bias unchanged): the latest closed close is measured inside the most recent Dow v2 swing leg. An up-leg (low, then high) reads `Fib <x>% of up-leg pullback` = (high − close) / (high − low); a down-leg (high, then low) reads `Fib <x>% of down-leg bounce` = (close − low) / (high − low). When the retracement is within `fib_tolerance` of 23.6, 38.2, 50, 61.8 or 78.6%, `, near <level>%` is appended. A close outside the leg reads `Close outside the latest swing leg (no Fibonacci zone)`.
- Values include both levels, their candle timestamps, and the distance in ATR and percent.

### 2. Advanced Dow + price action (PAPA Dow Theory Advanced; Candles Imp)

Compare the latest candle (C) with the previous candle (P). The trend (T) is the section 1 Dow trend before C. Terms follow the PAPA "Dow Theory Advanced" sheet (Bullish and Bearish Reversals, Trend Continuations). The row shows each label with its bias word (for example `Confirmation - Bullish`).

| Condition | Label | Bias |
| --- | --- | --- |
| P bearish, C bullish, C.close > P.close | `Confirmation: Close > Prev. Bearish Close` | bullish |
| P bearish, C bullish, C.close > P.low | `Confirmation: Close > Prev. Bearish Low` | bullish |
| P bearish, C bullish, C.close > P.high | `Continuation: Close > Prev. Bearish High` | bullish |
| P bullish, C bearish, C.close < P.close | `Confirmation: Close < Prev. Bullish Close` | bearish |
| P bullish, C bearish, C.close < P.high | `Confirmation: Close < Prev. Bullish High` | bearish |
| P bullish, C bearish, C.close < P.low | `Continuation: Close < Prev. Bullish Low` | bearish |
| C.close > P.high (any colour) | `Reversal Confirmation: Close > Prev. Candle High` | bullish |
| C.close > P.high, T down | `Down trend stopped` | bullish |
| C.close < P.low (any colour) | `Reversal Confirmation: Close < Prev. Candle Low` | bearish |
| C.close < P.low, T up | `Up trend stopped` | bearish |
| T up, C.close > P.low | `Bullish trend continues: Close above Prev. Candle Low` | bullish |
| T down, C.close < P.high | `Bearish trend continues: Close below Prev. Candle High` | bearish |

Bias follows the directional labels: bullish terms only → bullish, bearish terms only → bearish, otherwise neutral. Each price-action label retains its own direction in `label_bias`, and the UI shows the bias word on each tag.

Open observations are also listed when they apply: `Gap up` / `Bullish Open (above Prev. Close)` when the open is above the prior high / close; `Gap down` / `Bearish Open (below Prev. Close)` when below the prior low / close. Each is directional by its wording (bullish up, bearish down). Strong open/close observations (within 2% of the candle range) appear on the `candlestick_pattern` row, see below.

### 2a. Significant candle (PAPA Seminar key points, sheet "Significant candles")

Row `significant_candle`, placed after `candlestick_pattern`. A significant candle closes beyond the previous candle's High or Low, breaks a confirmed swing level, or gaps through one. The latest candle is checked against the 20 candles before it. Group A items only; Group B (3WS/3BC, counter attacks, sandwich, rounding, FBO/FBD, shakeouts, Ungli, news) is not yet evaluated.

| Item | Label | Bias |
| --- | --- | --- |
| Latest high above a significant candle high | `Takes out high of significant candle X (n candles ago)` | bullish |
| Latest low below a significant candle low | `Takes out low of significant candle X (n candles ago)` | bearish |
| Latest close above a significant high / below a significant low | `BO of significant candle X` / `BD of significant candle X` | bullish / bearish |
| Latest candle crosses a confirmed swing high / low | `Breaks out resistance X` / `Breaks down support X` | bullish / bearish |
| Gap up through a swing high / gap down through a swing low | `Gap up through resistance X` / `Gap down through support X` | bullish / bearish |
| Latest candle reaches back into an unfilled gap | `Fills exhaustion gap up/down` | neutral |
| Newest significant candle (stop-loss reference) | `Stop reference: significant candle high X, low Y` | neutral |
| Morning Star / Bullish Engulf / Hammer / Inverted Hammer at support | `<pattern> at major support` | bullish |
| Evening Star / Bearish Engulf / Inverted Hammer / Hanging Man at resistance | `<pattern> at major resistance` | bearish |
| Dow reversal or continuation confirmation on the price action row | `Dow reversal confirmation candle` / `Dow continuation confirmation candle` | as that label |
| BKT / BKP / BB challenge (Bollinger labels) | `BKT candle (upper band failure)`, `BKP candle (lower band failure)`, `BB challenge candle (upper/lower)` | bearish / bullish |
| RSI crosses 40 upward or 60 downward | `RSI brought above 40` / `RSI brought below 60` | bullish / bearish |
| Volume at least double the average on a breakout or breakdown | `High volume breakout` / `High volume breakdown` | bullish / bearish |
| Volume at least double the average at support or resistance | `High volume at major support` / `High volume at major resistance` | neutral |

Not yet built from this sheet: double top / bottom confirmation (needs a neckline-cross check), Stochastic crossover and PCO/NCO in MACD/Stoch/EMA/RSI (existing labels describe states, not the cross), and the mother-candle BO/BD (needs a definition).

### 2. Candlestick pattern and special candles (SMM Summary; PAPA Candles Imp)

The patterns below are shown on the `candlestick_pattern` row, with the pattern's bias. The `special_candles` row shows only whether the latest candle is at or near support or resistance (`At / near support`, `At / near resistance`, or `Not at support or resistance`), with neutral bias; the location bias sits on the location row.

Rules for the `candlestick_pattern` row (SMM Summary candlestick list; PAPA Candles Imp):

- **Normal candle:** when no other pattern matches, a close above the open is `Normal Bullish` (bullish bias) and a close below the open is `Normal Bearish` (bearish bias). No numeric rule is given in the source; this is the plain-candle reading chosen on 2026-10-23.
- **Middle of trend (PAPA):** a `Hammer` or `Inverted Hammer` in the middle of a trend or range (no support/resistance and no clear prior direction) is neutral with the note `Ignore mid-trend`.
- **Top / bottom of trend (PAPA):** a `Bullish Engulf` at the top, an `Inverted Hammer` at the bottom, and a `Bearish Engulf` at the bottom are shown with neutral bias and a note (`Not significantly bullish at top`, `Not significantly bearish at bottom`). A `Morning Star` at the top and an `Evening Star` at the bottom are neutral with `Caution for bulls at top` / `Caution for bears at bottom`. Elsewhere the bias is unchanged, and an unknown trend context keeps the fixed bias.
- **Strong candle (PAPA):** a candle with no upper or lower wick (Open = Low and Close = High for bullish, Open = High and Close = Low for bearish, within the wick tolerance) is `Strong Bullish Candle (no upper & lower wicks)` or its bearish mirror, with the matching bias. The four open/close observations are listed on this row when the combined label does not apply.

Morning Star (SMM Concepts 1, slide 33) needs a bearish first candle, a middle candle that opens with a gap-down below the first close and whose low is below the first low, and a bullish third candle that opens with a gap-up above the middle candle and closes above the first candle's midpoint. Evening Star is the mirror image (middle gaps up and its high is above the first high; third gaps down and closes below the first midpoint). The middle candle's colour and shape are not required, because SMM says it is "typically" neutral. Detected on the latest two/three candles: Bullish/Bearish Engulf, Bullish Piercing, Bearish Piercing (labelled Bearish Piercing (Dark Cloud Cover), the same PAPA candle), Hammer, Inverted Hammer, Hanging Man, Doji, Spinning Top, Morning Star, Evening Star, Mother candle (latest candle inside the previous candle's range), Bullish Harami and Bearish Harami (neutral; PAPA classes Harami as neutral, and the note says where it is significant: bullish at the bottom of a trend, bearish at the top), High Wave (small body with big wicks on both sides, neutral), Three White Soldiers and Three Black Crows (three candles closing progressively in one direction, each opening inside the prior real body). The label adds `in Support` / `at Resistance` when the location rule above says near. No pattern → `No special candle`, bias neutral.

- **Heikin-Ashi colour** (own row `heikin_ashi`, neutral bias): computed from the closed candles (HA close = (O+H+L+C)/4; HA open = average of the previous HA open and close, seeded with (O+C)/2). The latest HA candle reads `Heikin-Ashi green`, `Heikin-Ashi red` or `Heikin-Ashi doji`, followed by its wicks: `no wicks`, `upper wick`, `lower wick` or `both wicks` (PAPA Concept 3). A wick exists when the HA high is above the body top or the HA low is below the body bottom. Colour in the matrix (frontend `labelColor`): a candle with at most one wick is solid and takes its colour (green or red); a candle with both wicks is indecisive and shows yellow. Concept 2 (combining candles) is not applied to Heikin-Ashi.

### 3. Bollinger Band (PAPA BB Indicators Setups)

| Condition | Label | Bias |
| --- | --- | --- |
| High ≥ upper band and upper band expanding (signal candle) | `UBBC, BB Expands` | bullish |
| Low ≤ lower band and lower band expanding (signal candle) | `LBBC, BB Expands` | bearish |
| Upper band touched within `recent_crossover_periods` and upper band flat | `UBBC Failure, BKT` | bearish |
| Lower band touched within `recent_crossover_periods` and lower band flat | `LBBC Failure, BKP` | bullish |
| Otherwise | `Price is Above Median` / `Price is Below Median` / `Price is Near Median` | bullish / bearish / neutral |

**Signal candle:** the last closed candle when the latest candle is still forming, otherwise the latest candle. Touch and band-direction tests use the signal candle. A band that touches but contracts is not a failure: BKT / BKP need a flat band (PAPA source: "does not expand and becomes flat").

Appended to every Bollinger cell:

- Total width (latest candle): `Bands are Flat`, `Bands Expanding` or `Bands Contracting`.
- Side states (signal candle, every cell): `Upper band expanding` / `Upper band flat` / `Upper band contracting`, and the same for `Lower band`. A band is expanding when it moves more than `bb_flat_tolerance` in its outward direction over `slope_lookback` candles; flat when the move is within that tolerance; otherwise contracting.
- `Forming candle touches UBB` / `Forming candle touches LBB` when the still-forming latest candle reaches a band. This is a note only; it never sets `UBBC` or `LBBC`.
- `Beyond +3 SD band` / `Beyond -3 SD band` (see below).

Values: upper, basis, lower, band width, %B.

**All possible Bollinger values:**

| Group | Possible values | Bias |
| --- | --- | --- |
| State (one of, checked in this order) | `UBBC, BB Expands` (bullish), `LBBC, BB Expands` (bearish), `UBBC Failure, BKT` (bearish), `LBBC Failure, BKP` (bullish), `Price is Near Median` (neutral), `Price is Above Median` (bullish), `Price is Below Median` (bearish) | as shown in each label |
| Total width (one of) | `Bands are Flat`, `Bands Expanding`, `Bands Contracting` | neutral (no bias change) |
| Side states (one each) | `Upper band expanding` / `flat` / `contracting`; `Lower band expanding` / `flat` / `contracting` | neutral (no bias change) |
| Forming-candle notes (optional) | `Forming candle touches UBB`, `Forming candle touches LBB` | neutral (no bias change) |
| 3 SD excursions (optional) | `Beyond +3 SD band`, `Beyond -3 SD band` | neutral (no bias change) |

Three-standard-deviation excursions are appended as labels, bias unchanged: `Beyond +3 SD band` when High ≥ basis + 3σ, and `Beyond -3 SD band` when Low ≤ basis − 3σ, where σ = (upper − basis) / `bb_stddev`.

### 3. Divergence (RSI, MACD, Stochastic %K)

Own row, placed directly after EMAs. Its labels are collected from all three oscillators.

- Uses the last two confirmed price swings of closed candles: a swing high or low needs 5 bars before it and 2 bars after it (`divergence_confirm_bars`). The Dow pivots still wait 5 bars after, so divergence can see the latest top one refresh earlier. Bullish: the later swing low is lower than the earlier one while the oscillator's value at that candle is higher. Bearish: the later swing high is higher while the oscillator is lower.
- The oscillator is read at the exact bar of each swing; no tolerance band is applied.
- Reported only when the later pivot is within `divergence_lookback` candles.
- Labels `Bullish divergence (RSI)`, `Bullish divergence (MACD)`, `Bullish divergence (Stochastic %K)` and the matching `Bearish` labels are listed in the row. When none apply, the row shows `No divergence (RSI, MACD, Stochastic %K)`.
- Bias is always neutral: divergence is a warning to be read with the other indicator rows, not a trigger.
- Unavailable (`Needs two confirmed swing highs or lows.`) when fewer than two confirmed pivots exist in both highs and lows.

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

Every cell also shows the current value as `RSI <value>` rounded to two decimals (the same number stored in `values.rsi`).

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

Prefixed with `Raising` / `Falling` (compared with `slope_lookback`), e.g. `Raising > 12 or 15 (Gaining good strength in Trend)` / `Falling (Losing strength in Trend)` as in the worksheet. ADX is non-directional; bias follows DMI only when ADX is rising and ≥ 12, otherwise neutral. The current ADX value is shown as the last label (for example `ADX 26.50`), the same way RSI shows its value.

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
- Every cell also shows the current values as `%K <k> / %D <d>` (two decimals, the same numbers stored in `values.k` and `values.d`), directly after the headline.
- No recent crossover and neutral zone → `Not Clear`, neutral.

### 3. EMAs (SMM All Indicators; Summary)

- Price relation for each of 5, 13, 26, 50 (and 100/150/200 where available): `Price > 5`, `Price < 50`, …
- Stack: `POC, 5 > 13 > 26` / `NOC, 5 < 13 < 26`; long stack `POC, 100 > 150 > 200` / `NOC, 100 < 150 < 200`.
- Extended long stack: `POC, 5 > 50 > 100 and 50 > 200` / `NOC, 5 < 50 < 100 and 50 < 200`. These are appended labels; the colour rule above is unchanged.
- Crossover: `5 EMA PCO with 13 / 26 EMA` or `NCO` within the last 3 periods (SMM decision sheet).
- Colour (bias): bullish (green) when the 5 EMA is above 13 and 26 (`POC` / PCO state, 5 > 13 > 26); bearish (red) when below (`NOC` / NCO state, 5 < 13 < 26); otherwise neutral. Price relative to the 50 EMA is shown as a label but does not change the colour.
- Stack: `EMAs intermingled` when 5, 13 and 26 are not in a PCO or NCO order.
- Trend, classified line by line for each of 5, 13, 26, 50, 100, 150 and 200. The slope is the percentage change of that EMA over `slope_lookback` candles:
  - `Flat` when the absolute slope is at most `ema_flat_tolerance` (0.5%).
  - `Upward` / `Downward` when the slope is beyond the flat tolerance but below the steep tolerance.
  - `Steep upward` / `Steep downward` when the slope is at least `ema_steep_tolerance` (1.5%) in that direction.
- Labels group the periods by trend, for example `Flat EMAs: 5, 13, 26`, `Upward EMAs: 100, 150, 200`, `Steep downward EMAs: 5`. A period with no slope (insufficient candles) is left out of the groups.
- Values include `ema_<period>_slope_pct` and `ema_<period>_trend` (`flat`, `up`, `down`, `steep_up`, `steep_down`) for each period.

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

### 5. Volume of weapon candle

- Volume of the latest closed candle divided by the average volume of the 20 closed candles before it (`volume_ratio`).
- Labels: `Less than average volume` (below 0.8×), `Average volume` (0.8× to 1.2×), `More than average volume` (1.2× to 2×), `Double average volume (high)` (2× or more), plus `<ratio>x the 20-candle average`. Bias neutral.
- Unavailable (with a reason) when the source supplies no volume for that timeframe.

### 5. Chart patterns (Double Top / Double Bottom)

- Uses confirmed pivots of closed candles within `pattern_lookback`. A double top needs two peaks within `double_top_tolerance` of each other, at least `double_top_min_gap` candles apart, with a neckline (the lowest low between the peaks) at least `double_top_tolerance` below them.
- Latest closed close above or below the neckline decides the state. Double top: `Double Top candidate, neckline <x> holding` (neutral) while the close is above the neckline, `Double Top, neckline <x> broken` (bearish) once it closes below. Double bottom mirrors this with `Double Bottom ...` and a bullish break.
- No qualifying pair → `No double top / bottom`, neutral. Other chart patterns remain manual.

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
- Only symbols in the recorded `PS_Commodity` snapshot are accepted. Others return 422.
- `GET /api/v1/mtf-analysis/instruments` returns the snapshot: sections in watchlist order, each with its symbols, plus `default_symbol` (`PEPPERSTONE:NATGAS`) and the snapshot's `recorded_at`.

### Instrument snapshot

- The watchlist is read **once, read-only**, through the TradingView Desktop page's own custom-list endpoint (`GET /api/v1/symbols_list/custom/`), which does not change the active watchlist, chart, or layout.
- The snapshot is stored in the repository (`src/god_market_api/data/mtf_watchlist.json`) with the watchlist name, default symbol, section names, symbol order, and `recorded_at`. Section markers (`###…`) become section names with invisible characters removed.
- `scripts/sync-mtf-watchlist.mjs --list <name> --default <symbol>` re-reads the list on request and rewrites the snapshot; it never writes to TradingView. The default symbol must be in the list.
- Market data for every instrument still comes from the official MCP through the existing orchestrator.

Snapshot recorded 2026-10-13 (16 instruments, `PS_Commodity`, default `PEPPERSTONE:NATGAS`):

| Section | Symbols |
| --- | --- |
| INTERNATIONAL - STUDY, TA ANALYSIS | PEPPERSTONE:NATGAS, TVC:GOLD, TVC:UKOIL, TVC:USOIL, TVC:SILVER, CAPITALCOM:COPPER |
| INDIA MCX | MCX:NATURALGAS1!, MCX:GOLD1!, MCX:GOLDPETAL1!, MCX:CRUDEOIL1!, MCX:CRUDEOILM1!, MCX:GOLDGUINEA1!, MCX:SILVER1!, MCX:SILVERMIC1!, MCX:SILVERM1!, MCX:NATGASMINI1! |

The previous snapshot (`PS_DailyWatch_Favourite`, 32 NSE instruments, recorded 2026-10-09) was replaced on request.

## UI

- New primary navigation item **Multi-Timeframe** at `/multi-timeframe`, next to **Global Market**; same header, theme switcher, and footer.
- Controls: searchable instrument dropdown grouped by the `PS_Commodity` sections (default NATGAS, `PEPPERSTONE:NATGAS`), last-updated time, live status tag (see Live updates), Refresh. The selected symbol is kept in the URL (`?symbol=PEPPERSTONE:NATGAS`).
- Headline strip: Double Screen (Tide + Wave) and Triple Screen decisions with the disclaimer.
- Matrix: sticky checklist column; grouped column headers per layer with timeframe sub-columns; each cell shows compact tags coloured by bias (bullish green, bearish red, neutral grey, unavailable dashed); manual rows show a muted `Manual check` tag.
- Per-timeframe header shows source, freshness badge, and `Live candle`.
- Clicking a cell opens a drawer with raw values, rule wording, and candle timestamps.
- Responsive: horizontal scroll for the matrix on narrow screens; keyboard focusable cells; light/dark theme via existing tokens.

## Live updates (WebSocket, protocol v1)

Decided 2026-10-15: live means a checklist push when each timeframe's candle closes, plus a refresh of candles still forming while their session is open. The official TradingView MCP is tool-call based with no streaming-price feed, so the backend pushes what it fetches itself. Nothing uses TradingView's internal chart WebSocket.

**Endpoint:** `GET /api/v1/mtf-analysis/{symbol}/live` (WebSocket). Unknown instruments are refused with close code 1008 before the socket is accepted.

**Envelope** (`version` = 1), one JSON object per message:

| Field | Meaning |
| --- | --- |
| `type` | `snapshot` (first message, current analysis), `update` (new analysis), `heartbeat` (no analysis), `error` (refresh failed; the message says so) |
| `reason` | `subscribed`, `candle_close` (at least one timeframe got a new candle), or `forming_refresh` |
| `closed_timeframes` | Timeframes whose candle closed since the previous message |
| `analysis` | Same shape as `GET /api/v1/mtf-analysis/{symbol}`; present for `snapshot` and `update` |
| `sent_at`, `symbol`, `error` | Server time, normalised symbol, error text when `type` is `error` |

**Refresh schedule** (one loop per symbol, shared by every open dashboard):

| Setting | Default | Meaning |
| --- | ---: | --- |
| `forming_interval` | 60 s | A candle still forming is re-fetched this often; the refresh is pulled forward to its close. |
| `retry_interval` | 60 s | After a candle closes but before the source publishes the next one, retry at this interval. |
| `retry_limit` | 5 | Number of retries before switching to the idle interval. |
| `idle_interval` | 10 min | Slow poll until a new candle appears (e.g. overnight, or after a weekend). |
| heartbeat | 30 s | Sent when nothing else was sent in the last 30 seconds, so proxies and the browser see a live socket. |

Refreshes bypass the cache for the timeframes that are due (`force_refresh`); all other timeframes are read from the cache as usual. Every refresh still goes through the configured source (official MCP primary, Desktop fallback, per ADR-002).

**Cost:** each forming-candle cycle re-fetches every timeframe that is still forming. For a 24-hour CFD such as `PEPPERSTONE:NATGAS` that is usually four or more calls per minute while a dashboard is open, and each cycle can take tens of seconds on the source. Watch the source's rate limits before raising the subscriber count or lowering `forming_interval`.

**Browser behaviour:** the page connects when an instrument is selected and writes each `snapshot` or `update` into the same cache entry the page renders from, so the matrix updates without a refetch. A status tag shows `Connecting`, `Live` or `Reconnecting`. On a dropped socket it reconnects with exponential backoff (1 s, doubling, capped at 30 s). When no message arrives for 90 seconds the socket is treated as dead and reconnected. While reconnecting, a warning shows the time of the last update; `Refresh Data` still fetches on demand.

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
- **Ask first:** adding symbols outside the watchlist snapshot; adding new dependencies (no new Python/JS dependency is planned); changing existing API contracts; enabling heuristic chart-pattern detection beyond Double Top / Double Bottom (approved for those two only).
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
| Symbols | All instruments in the recorded watchlist, grouped by section. Initially `PS_DailyWatch_Favourite` with Nifty 50 by default; changed on 2026-10-13 to `PS_Commodity` with NATGAS (`PEPPERSTONE:NATGAS`) by default |
| Watchlist access | One-time read-only snapshot stored in the app; refreshed on request by a script |
| Subjective rows | Shown as `Manual check`, not automated |
| Wording | Worksheet wording (BUY / SELL / NOT CLEAR, Up Tick, PCO state) with a not-advice caption |
| Columns | Eight columns in four layers, as in the worksheet |
| Candle | Latest candle even if forming, labelled live |
| Thresholds | Defaults above, configurable in the profile |
| Bollinger basis | Standard SMA basis kept, even though the user's chart uses an EMA basis (difference 0.04% on validation) |
| Added checklist evidence | Nine items approved on 2026-10-15 as labels inside existing rows (no new rows). Divergence, volume, breakout, Fibonacci, Heikin-Ashi, 3 SD and extended EMA stack labels leave bias unchanged; Double Top / Bottom sets bias only on a neckline break |
| Divergence confirmation | Divergence swings confirm after 2 closed bars instead of 5 (`divergence_confirm_bars`), chosen by the user on 2026-10-16. Reason: the 5-bar rule hid the 16 Oct 1H top (57.94, %K 94.4 vs 57.53, %K 94.6), so 1H showed a stale bullish label. Dow structure keeps 5 bars |
| Divergence row | Divergence moved out of the RSI, MACD and Stochastic rows into its own row directly after EMAs, so the three oscillator readings and their divergence sit in one place. Neutral bias. This supersedes the "no new rows" wording above for divergence only |
| Heikin-Ashi and candlestick rows | Heikin-Ashi moved out of `price_action` into its own row (neutral bias). Candlestick patterns moved out of `Special candles` into their own row; `Special candles` now shows the support/resistance location only (neutral bias). Approved 2026-10-23. Supersedes the "no new rows" wording above for these two items only |
| Candlestick rules (SMM + PAPA) | Plain candles are `Normal Bullish` / `Normal Bearish`. Top/bottom rules set neutral bias for Engulf, Inverted Hammer, Morning Star and Evening Star at the weaker end of the trend. Strong no-wick candles and their open/close observations moved from the `price_action` row to the `candlestick_pattern` row. Approved 2026-10-23 |

## Open questions

- Indices (`NSE:NIFTY`, `NSE:BANKNIFTY`, `NSE:INDIAVIX`) have no volume on TradingView; volume evidence is shown only when candles carry volume.
- `NSE:INDIAVIX` is a volatility index; the checklist is calculated the same way but its bias colours do not mean market direction. The UI shows a note for it.
- MCX session close is taken as 23:30 IST; the 23:55 schedule during US daylight-saving time is not modelled. Holiday calendars are not modelled for any exchange.
- Angular trendlines and chart patterns other than Double Top / Double Bottom are manual; any further heuristic detection needs separate approval.
