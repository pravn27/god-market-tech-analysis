# E-04 Technical Enrichment — implementation plan

## Goal

Provide deterministic, explainable technical evidence from the OHLCV context delivered by E-02/E-03, without adding strategy interpretation.

## Task 1 — Define indicator profile and evidence contracts

**Acceptance:** Versioned settings define the initial indicator periods; every evidence group can be available or explicitly unavailable; contracts carry source-context linkage but no recommendation field.

**Verification:** `uv run pytest -q tests/test_technical_models.py`; full suite passes.

## Task 2 — Implement core series calculations

**Scope:** EMA, RSI, MACD, Bollinger Bands.

**Acceptance:** Fixed OHLCV fixtures yield checked latest values; insufficient data returns typed unavailable evidence; no provider calls occur.

**Verification:** `uv run pytest -q tests/test_technical_indicators.py`; full suite passes.

## Task 3 — Implement momentum-strength calculations

**Scope:** DMI/ADX and Stochastic.

**Acceptance:** Fixed fixtures and zero-range/short-series cases are deterministic and explicit.

**Verification:** `uv run pytest -q tests/test_technical_indicators.py`; full suite passes.

## Task 4 — Add structure and location evidence

**Scope:** Pivot-based trend structure and transparent support/resistance candidates.

**Acceptance:** Each candidate identifies its contributing pivots and lookback; no candidate is labelled a trade signal.

**Verification:** `uv run pytest -q tests/test_price_structure.py`; full suite passes.

## Task 5 — Expose opt-in local enrichment API

**Acceptance:** A fixture-backed endpoint returns raw source context plus derived evidence; raw E-03 endpoints are unchanged; unavailable source contexts remain safe.

**Verification:** `uv run pytest -q tests/test_technical_api.py`; full suite passes; inspect generated local OpenAPI schema.

## Task 6 — Record read-only validation evidence

**Acceptance:** One authorized source context is enriched locally, calculation profile/version and warnings are recorded, and no OAuth data is retained in validation evidence.

**Verification:** full suite plus a local read-only request.

## Dependencies and guardrails

- E-03 cache/orchestrator remains the sole multi-timeframe data coordinator.
- Technical calculations are pure local functions; they accept models and return models.
- Rule thresholds and setup logic belong to E-07/E-08, not this epic.
- One task at a time; run focused and full tests before moving forward.
