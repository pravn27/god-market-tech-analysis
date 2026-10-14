# Specification: Dow Structure v2

Status: **Approved 2026-10-14; implemented**

## Objective

Add richer, non-repainting Dow Theory evidence to the Multi-Timeframe checklist
without changing the existing `mtf-checklist-v1` result or any Double/Triple
Screen decision.

The existing row remains the ASTA-compatible summary:

- `HH - HL (Up Trend)`
- `LL - LH (Down Trend)`
- `HLs - LHs (Sideways Trend)`

An additive **Dow structure v2 (closed candles)** row explains whether a mixed
structure is contracting, expanding, equal/transitional, or a possible
structure break. It remains context evidence, not a BUY/SELL instruction.

## Sources

### ASTA

The approved extraction in
[`mtf-analysis-checklist.md`](mtf-analysis-checklist.md) is authoritative:

- two confirmed swing highs and two confirmed swing lows;
- `HH + HL` is bullish;
- `LH + LL` is bearish;
- other combinations are not a confirmed directional trend;
- Advanced Dow price action and broken support/resistance ("impact line") are
  supporting evidence.

The original knowledge-source workbooks are not stored in this repository.
This feature must not invent a new ASTA rule that is absent from the approved
extraction.

### TradingView

- [Pivot Points High Low](https://www.tradingview.com/support/solutions/43000589195-pivot-points-high-low/)
  confirms pivots from lower highs or higher lows on both sides.
- [Zig Zag](https://www.tradingview.com/support/solutions/43000591664-zig-zag/)
  documents alternating confirmed pivots, a reversal-deviation filter, and
  confirmation lag. Its Pivot legs = 10 example uses five bars on each side
  with the same strict-left/non-strict-right comparison as the existing code.
- [Pine Script v6 reference](https://www.tradingview.com/pine-script-reference/v6/)
  documents `ta.pivothigh` and `ta.pivotlow`.

TradingView indicators are validation references only. The application
continues to calculate from normalized official-MCP OHLCV.

## Assumptions

1. The existing v1 Dow row and its labels remain unchanged.
2. V2 is additive and initially visible side by side with v1.
3. Structural pivots use closed candles only. Other checklist rows continue to
   use the latest candle and retain the existing `live_candle` badge.
4. The confirmed pivot window remains five bars left and five bars right.
5. ATR significance is evidence only; it does not alter the ASTA structure.
6. No TradingView chart, indicator, watchlist, timeframe, or layout is changed.

## Functional contract

### 1. Closed-candle input

For each timeframe:

- if the latest candle is live, omit only that candle from v2 structure
  calculation;
- if the latest candle is closed, include it;
- v1 and all existing indicator rows keep their current input and behaviour;
- expose `used_closed_candles` and `excluded_live_candle` in v2 raw values.

This prevents a forming candle from invalidating the newest v2 pivot while
keeping live price-action evidence available elsewhere.

### 2. Confirmed pivot candidates

Reuse the existing `find_pivots(..., left=5, right=5)` rule:

- pivot high: strictly greater than the five left highs and greater than or
  equal to the five right highs;
- pivot low: strictly lower than the five left lows and lower than or equal to
  the five right lows.

The newest candidate therefore appears only after five right-side candles. The
v2 cell must expose this five-bar confirmation lag.

### 3. Alternating swing normalization

Merge confirmed highs and lows in candle order.

- Consecutive highs without an intervening low collapse to the higher high.
- Consecutive lows without an intervening high collapse to the lower low.
- If one candle is both a pivot high and pivot low, its intrabar order is
  unknowable from OHLCV. Omit that ambiguous pair and expose a warning/count;
  do not guess its order.
- The resulting sequence must alternate high, low, high, low (or the reverse).

V1 continues to compare its independent high and low lists and is not changed
by this normalization.

### 4. V2 structure classification

Compare the last two normalized highs and last two normalized lows:

| High relation | Low relation | V2 structure | Bias |
| --- | --- | --- | --- |
| HH | HL | `HH - HL (Up Trend)` | bullish |
| LH | LL | `LL - LH (Down Trend)` | bearish |
| LH | HL | `LH - HL (Contracting Range)` | neutral |
| HH | LL | `HH - LL (Expanding Range)` | neutral |
| either relation equal | any | `Equal / Transitional Structure` | neutral |
| fewer than two of either swing | | unavailable | unavailable |

V2 does not call a mixed structure a confirmed reversal.

### 5. Break-of-structure evidence

Use the latest **closed** candle close and the latest confirmed normalized
swing levels:

- close above the latest swing high: `Bullish structure break`;
- close below the latest swing low: `Bearish structure break`;
- otherwise: `No confirmed structure break`.

Interpretation:

| Established v2 structure | Break direction | Label |
| --- | --- | --- |
| Up | bullish | `Bullish continuation (BOS)` |
| Down | bearish | `Bearish continuation (BOS)` |
| Down | bullish | `Possible bullish change of character` |
| Up | bearish | `Possible bearish change of character` |
| Range/transition | either | directional structure break only |

“Possible change of character” is evidence of transition. It does not change
the trend to the opposite direction until the required HH+HL or LH+LL sequence
is confirmed.

### 6. ATR significance evidence

For the two compared highs and lows, return:

- `high_delta_atr = abs(last_high - previous_high) / ATR(14)`;
- `low_delta_atr = abs(last_low - previous_low) / ATR(14)`;
- `structural_moves_significant = true` only when both are at least
  `dow_significance_atr` (default `0.5`).

If ATR is unavailable, structure still calculates and significance is
unavailable. This evidence must not change the structure or bias.

### 7. Cell evidence

The additive v2 checklist cell returns:

- labels: v2 structure, break/transition label, and an ambiguity warning when
  applicable;
- bias: bullish only for confirmed uptrend, bearish only for confirmed
  downtrend, neutral for range/transition, unavailable for insufficient swings;
- values:
  - previous/latest swing high and low prices;
  - their candle timestamps;
  - latest closed candle timestamp and close;
  - high/low movement in ATR;
  - confirmation lag;
  - closed-candle count;
  - whether a live candle was excluded;
  - ambiguous pivot count;
- rule IDs: `dow-v2`, `dow-v2-break`, and `dow-v2-significance` where
  applicable.

## UI and API

- Add one automated checklist row immediately after the existing Dow trend row:
  **Dow structure v2 (closed candles)**.
- Reuse the existing checklist-cell API shape; no endpoint or existing field is
  removed or renamed.
- The detail drawer shows all v2 raw evidence through its current generic
  values renderer.
- The existing v1 row remains the primary compatibility result.
- Screen decisions do not consume v2 in this release.
- The response profile remains `mtf-checklist-v1`; v2 identifies itself through
  its row ID and rule IDs until the user approves making it the default.

## TradingView validation

Automated:

1. Fixed OHLCV fixtures prove the documented five-left/five-right pivot
   comparisons.
2. Fixtures prove alternating same-leg extreme selection.
3. Fixtures cover up, down, contracting, expanding, equal/transitional,
   bullish/bearish BOS, possible change of character, ambiguous outside-bar,
   insufficient swings, and live-candle exclusion.
4. Existing v1 tests remain unchanged and passing.

Manual/read-only:

- Compare displayed swing points with an already-present TradingView Pivot
  Points High Low/Zig Zag indicator when available.
- Do not add an indicator or change chart state automatically.
- An optional Pine v6 validation script may be documented for the user to run
  manually; it is not executed by the application.

## Commands

```text
Focused structure: uv run pytest -q tests/test_price_structure.py
Focused checklist: uv run pytest -q tests/test_mtf_checklist.py tests/test_mtf_analysis_api.py
Backend full:      uv run pytest -q
Frontend:          cd frontend && npm run lint && npm run typecheck && npm test -- --run && npm run build
```

## Project structure

```text
src/god_market_api/price_structure.py  v2 swing normalization and structure
src/god_market_api/mtf_checklist.py    threshold, row and v2 cell mapping
src/god_market_api/mtf_analysis.py     live/closed-candle input selection
tests/test_price_structure.py          pure v2 structure tests
tests/test_mtf_checklist.py            cell evidence tests
tests/test_mtf_analysis_api.py         live-candle/API compatibility tests
frontend/...                           fixture/test update only if the new row requires it
```

## Boundaries

- **Always:** preserve v1 output; show exact evidence; use deterministic pure
  functions; keep TradingView read-only; mark insufficient evidence
  unavailable.
- **Ask first:** make v2 the primary/default Dow result; feed v2 into screen
  decisions; change pivot window; introduce a percentage-deviation filter.
- **Never:** infer intrabar order from OHLCV; declare a reversal from one
  opposite break; use MACD/ADX/EMA as Dow Theory; mutate a TradingView chart;
  present the result as trade advice.

## Success criteria

1. Existing v1 Dow labels and all existing API fields remain compatible.
2. V2 distinguishes up, down, contracting, expanding and equal/transitional
   structures from an alternating confirmed swing sequence.
3. A live candle is excluded only from v2 structural evidence.
4. Break evidence distinguishes continuation BOS from possible change of
   character without prematurely reversing the trend.
5. ATR significance is visible but cannot change structure or bias.
6. Focused and full backend tests pass; frontend checks pass if fixtures change.
7. No TradingView state is changed during validation.

## Deferred decisions

- Whether v2 should replace the v1 row after side-by-side review.
- Whether a later profile should use a TradingView-style reversal percentage
  or a timeframe-specific pivot window.
- Whether Dow v2 should contribute to Double/Triple Screen decisions.
