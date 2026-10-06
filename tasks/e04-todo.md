# E-04 Technical Enrichment — task checklist

## Task 1: Indicator profile and evidence contracts

- [ ] Versioned default settings exist for EMA, RSI, MACD, Bollinger Bands, DMI/ADX, and Stochastic.
- [ ] Evidence contracts distinguish available values from typed unavailable outcomes.
- [ ] Contracts contain no setup score, recommendation, or trade direction.
- [ ] Focused tests pass: `uv run pytest -q tests/test_technical_models.py`.
- [ ] Full test suite passes: `uv run pytest -q`.

## Task 2: Core series calculations

- [ ] EMA, RSI, MACD, and Bollinger values match fixed fixtures.
- [ ] Insufficient or invalid data produces explicit unavailable evidence.
- [ ] Focused tests pass: `uv run pytest -q tests/test_technical_indicators.py`.
- [ ] Full test suite passes: `uv run pytest -q`.

## Task 3: Momentum-strength calculations

- [ ] DMI/ADX and Stochastic values match fixed fixtures.
- [ ] Zero-range and short-series behaviour is explicit.
- [ ] Focused tests pass: `uv run pytest -q tests/test_technical_indicators.py`.
- [ ] Full test suite passes: `uv run pytest -q`.

## Task 4: Structure and location evidence

- [ ] Pivot evidence supports trend-structure classification without a trade recommendation.
- [ ] Support/resistance candidates retain their contributing pivots and configuration.
- [ ] Focused tests pass: `uv run pytest -q tests/test_price_structure.py`.
- [ ] Full test suite passes: `uv run pytest -q`.

## Task 5: Local enrichment API

- [ ] Fixture-backed API response returns source context and local derived evidence.
- [ ] Existing raw context endpoints remain compatible.
- [ ] Focused tests pass: `uv run pytest -q tests/test_technical_api.py`.
- [ ] Full test suite passes: `uv run pytest -q`.

## Task 6: Live read-only validation

- [ ] Derived evidence is checked against an authorized source context.
- [ ] Calculation profile/version and warnings are recorded without OAuth data.
- [ ] Full test suite passes: `uv run pytest -q`.
