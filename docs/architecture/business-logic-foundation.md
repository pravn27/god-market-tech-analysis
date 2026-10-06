# Business Logic Backend foundation

## Purpose

This is the lasting Python foundation for the Business Logic Backend Service in the high-level design. It keeps TradingView access, multi-timeframe coordination, deterministic trading rules, persistence, and UI delivery separate so the planned epics can be added without creating one large service module.

## Design principles

- **Local first:** bind services to localhost; secrets remain in the OS keychain.
- **Evidence first:** every derived result retains symbol, timeframe, source, source timestamp, freshness, and rule-set version.
- **Deterministic rules:** the same recorded context and setup version produce the same evaluation.
- **Partial data is explicit:** unavailable or stale context must not become neutral or bullish/bearish by accident.
- **Source isolation:** only adapters understand official MCP or Desktop bridge response shapes.
- **No execution:** no broker, order, or automated/semi-automated trading capability.

## Layered modules

```text
src/god_market_api/
├── api/                 # HTTP and later WebSocket routes; validates requests only
├── application/         # use cases: refresh MTF context, evaluate setup, query history
├── domain/              # pure models, policies, rules, scores, state transitions
├── infrastructure/
│   ├── tradingview/     # official MCP and Desktop-bridge adapters
│   ├── cache/           # local TTL cache and request-budget implementation
│   └── persistence/     # SQLite repositories and migrations, added when E-11 begins
├── contracts/           # versioned API/event request and response models
└── bootstrap.py         # dependency wiring and configuration
```

Current `app.py`, `models.py`, `oauth.py`, and `providers.py` are the Phase 1 foundation. E-03 should introduce the new folders incrementally rather than moving working code merely for appearance.

## Dependency direction

```text
API / WebSocket → Application use case → Domain policy and rules
                                       → Adapter/cache/persistence ports
Infrastructure adapters → external TradingView MCP or local Desktop bridge
```

- The domain never imports FastAPI, HTTP clients, keyring, or TradingView types.
- Application services accept ports/protocols, never raw MCP responses.
- Adapters return normalized `ChartContext` only.
- API and WebSocket layers convert typed contracts into transport responses; they do not calculate indicators or scores.

## Core contracts

| Contract | Responsibility |
| --- | --- |
| `ChartContextProvider` | Obtain one normalized symbol/timeframe context from a named source. |
| `MultiTimeframeContext` | One symbol's requested contexts, layer summaries, overall completeness, and refresh metadata. |
| `FreshnessPolicy` | Decide `ready`, `stale`, or `unavailable` from timeframe-specific limits and source timestamps. |
| `IndicatorCalculator` | Pure calculations from normalized OHLCV; introduced in E-04. |
| `Rule` / `RuleResult` | Pure setup decision and evidence; introduced in E-07. |
| `SetupRepository` / `EvaluationRepository` | Versioned setup definitions and local history; introduced in E-08/E-11. |
| `EventPublisher` | Publish versioned local update events; introduced in E-12. |

## Reliability and request budget

- Reuse one context when it appears in multiple decision layers (for example, 4H in TIDE and WAVE); never fetch it twice in a single refresh.
- Apply a local concurrency limit and cache successful contexts by `source + symbol + timeframe`.
- Treat TradingView's documented request budget as a shared resource. Batch or stagger refreshes; do not allow every browser refresh to fan out independently.
- Cache policy, maximum staleness, retry count, and refresh interval are configuration values, not embedded trading rules.
- A failed technical snapshot may accompany usable OHLCV only when the response says so clearly; it never receives invented values.

## Observability and privacy baseline

For every refresh, record structured non-secret fields: request ID, symbol, timeframe, active source, cache outcome, source timestamp, freshness state, duration, and sanitized failure category. Never log OAuth codes, access tokens, refresh tokens, or full authorization URLs.

## Quality gates for every epic

1. A feature specification and API/event contract are approved before runtime code.
2. Domain policies have deterministic unit tests and recorded fixtures.
3. Adapter boundaries have contract tests for success, stale, unavailable, and rate-limited responses.
4. Integration tests verify the intended application use case without a live TradingView dependency.
5. A live read-only check and manual chart-verification record are added when the feature consumes market data.
6. Review checks security, source/freshness evidence, local-only scope, and rollback behaviour before commit.
