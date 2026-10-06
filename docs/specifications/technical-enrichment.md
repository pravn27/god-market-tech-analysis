# Specification: technical enrichment

## Product outcome

Transform a source-attributed `ChartContext` into transparent, local technical evidence that later multi-timeframe views and deterministic setup rules can consume.

This feature calculates from the normalized OHLCV already received from TradingView. It does **not** request additional market data, place trades, infer a setup, produce a readiness score, or issue alerts.

## Inputs and boundaries

- Input: one `ChartContext` with ordered OHLCV candles, source timestamp, and freshness state.
- Output: typed technical evidence containing values, availability, settings version, and explanatory warnings.
- Calculation location: local business-logic backend only.
- Source fidelity: retain the original source, timestamps, OHLCV, and provider warnings. Derived values must be distinguishable from source-provided technical summaries.
- Insufficient candles, gaps, non-finite values, or unavailable context produce typed unavailable evidence. They never produce substituted values.

## Initial indicator profile

The first profile is configurable and versioned. These defaults are evidence conventions, not trading decisions:

| Evidence group | Initial settings | Initial output |
| --- | --- | --- |
| EMA | 5, 13, 26, 50 periods | latest EMA values and price relation |
| RSI | 14 periods | latest RSI and raw availability |
| MACD | 12 / 26 / 9 | line, signal, histogram |
| Bollinger Bands | 20 periods, 2 standard deviations | upper, middle, lower, price location |
| DMI / ADX | 14 periods | +DI, -DI, ADX |
| Stochastic | 14 / 3 / 3 | %K and %D |

No label such as “buy,” “sell,” “strong,” or “entry confirmed” belongs to this epic. Later rules may interpret the evidence under their own explicit, versioned policy.

## Incremental delivery

1. Define versioned calculation settings and typed evidence contracts.
2. Add pure EMA, RSI, MACD, and Bollinger calculations, including insufficient-data outcomes.
3. Add pure DMI/ADX and Stochastic calculations with fixture and edge-case tests.
4. Add price-structure and support/resistance evidence as separate, explainable calculations.
5. Add an opt-in local API enrichment response without changing the existing raw-context response.
6. Verify one read-only live source context locally and record the derived-evidence limitations.

## Acceptance criteria

1. The same ordered OHLCV fixture and settings version always return the same evidence.
2. Every derived value identifies its calculation profile and has enough raw-input evidence for later drill-down.
3. Insufficient or invalid data is explicit and does not masquerade as neutral or current.
4. Existing `/api/v1/chart-context` and `/api/v1/multi-timeframe-context` contracts remain unchanged.
5. No technical-enrichment output is framed as financial advice or a trade instruction.

## Validation

- Unit tests use fixed OHLCV fixtures with independently checked expected values.
- Edge-case tests cover empty, short, unordered, duplicate-timestamp, and non-finite candles.
- API contract tests use fixture providers only.
- A live read-only check confirms derivation runs locally from a source-attributed context; it does not validate a trading outcome.
