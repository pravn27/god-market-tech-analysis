# Specification: multi-timeframe context orchestration

## Product outcome

For one exchange-qualified symbol, provide a single local response that supplies the evidence needed by the future Confluence Board: Monthly, Weekly, Daily, 4H, 1H, and 15m context, together with source, source timestamp, freshness, and availability for every timeframe.

This is a data-coordination feature. It does not classify trades, calculate a setup score, create alerts, or give trading instructions.

## Inputs and output

### Inputs

- `symbol`: required TradingView `EXCHANGE:TICKER` value.
- `timeframes`: optional subset of the six configured timeframes; default is all six.
- `refresh_mode`: `prefer_cache` by default; `force_refresh` is local-user initiated and subject to the request budget.

### Output contract

```text
MultiTimeframeContext
  symbol
  requested_at
  source_summary
  completeness: complete | partial | unavailable
  contexts[Monthly, Weekly, Daily, 4H, 1H, 15m]
    ChartContext | unavailable reason
  layers
    Super TIDE: Monthly + Weekly
    TIDE: Daily + 4H
    WAVE: 4H + 1H
    Ripple / Super Ripple: 1H + 15m
  warnings[]
```

Each successful `ChartContext` continues to carry its own source, source timestamp, freshness state, OHLCV, technical-snapshot availability, and warnings. The same 4H or 1H context is referenced by two layers; it is fetched once per refresh.

## Behaviour

1. Validate the symbol and requested timeframe set before calling a provider.
2. Resolve each unique timeframe through the official MCP provider first.
3. Read a valid local cached context before making a remote request unless `force_refresh` is requested.
4. Enforce a bounded local concurrency limit. A persistent/shared TradingView request budget is planned before monitoring is enabled.
5. Determine freshness from the source timestamp and a configurable freshness policy—not merely the time the backend received data.
6. Return successful contexts even when one or more timeframes fail. Mark the aggregate as `partial` and include a clear reason per failed timeframe.
7. Return `unavailable` only when no requested timeframe can supply usable context.
8. Do not silently use the Desktop bridge. A fallback policy and source label are required before it is enabled.

### Local request guardrails

- The initial provider concurrency limit is **three** timeframe requests per local service instance. It is configurable at construction time and must remain a backend operational setting, not a trading rule.
- Identical in-progress requests for the same source, symbol, and timeframe share one provider operation. A cancelled dashboard request does not cancel that shared source request.
- A failure for one timeframe becomes that timeframe's typed unavailable result; it never cancels other timeframe requests in the same refresh.

## Initial cache and freshness policy

Initial values are safe defaults and must be configurable before monitoring begins:

| Timeframe | Cache target | Freshness target |
| --- | ---: | ---: |
| Monthly | 6 hours | 14 days |
| Weekly | 2 hours | 8 days |
| Daily | 15 minutes | 36 hours |
| 4H | 10 minutes | 8 hours |
| 1H | 5 minutes | 2 hours |
| 15m | 2 minutes | 45 minutes |

Market holidays and exchange sessions can make a timestamp appear old. E-03 reports this condition; calendar-aware exceptions are a later enhancement and must never mark a stale context as ready without evidence.

## Failure behaviour

| Situation | Required behaviour |
| --- | --- |
| OAuth is absent or expired | No fabricated context; return actionable source-unavailable state. |
| Provider rate limit | Use a still-valid cache if available; otherwise mark only that timeframe unavailable and apply retry/backoff. |
| OHLCV succeeds; technical snapshot fails | Return OHLCV with a visible partial-data warning. |
| One timeframe fails | Return the other contexts and aggregate `partial`; no implicit neutral interpretation. |
| All timeframes fail | Aggregate `unavailable`; dashboard must show recovery guidance. |
| User forces refresh repeatedly | Coalesce duplicate in-flight work; persistent request-budget enforcement is a planned operational enhancement. |

## Acceptance scenarios

| Scenario | Expected result |
| --- | --- |
| All six contexts current | One complete response with six source-attributed contexts and four layer views. |
| 4H requested by two layers | One provider request/cached lookup for 4H; both layers reference the same result. |
| 15m source unavailable | Other contexts remain visible; aggregate is `partial`; Ripple layer is qualified. |
| Rate limit with valid Daily cache | Cached Daily context is returned with cache/freshness evidence and a warning. |
| OAuth missing | No provider call succeeds; aggregate is `unavailable` with safe recovery detail. |
| Forced refresh while identical refresh is active | Work is shared or rejected safely; request budget is not doubled. |

## Validation evidence

- Unit tests: timeframe selection, deduplication, completeness, freshness, and cache policy.
- Contract tests: provider success, unavailable, stale, and rate-limited payloads.
- Integration tests: one use case over six fixture contexts without TradingView network access.
- Manual read-only verification: record an approved symbol, all source timestamps, and the dashboard/API result in the chart-verification template.
