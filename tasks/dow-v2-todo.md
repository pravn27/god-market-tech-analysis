# Dow Structure v2 — task checklist

## Task 1: Pure structure model

- [x] Normalize confirmed pivots into an alternating sequence.
- [x] Classify up, down, contracting, expanding and transition structures.
- [x] Report BOS/change-of-character and ATR significance evidence.
- [x] Verify: `uv run pytest -q tests/test_price_structure.py`.

## Checkpoint: pure model

- [x] Existing v1 tests remain unchanged and pass.
- [x] New v2 edge cases pass.

## Task 2: Checklist integration

- [x] Add the side-by-side v2 checklist row.
- [x] Preserve v1 inputs and labels.
- [x] Expose raw v2 evidence in the existing cell contract.
- [x] Verify: `uv run pytest -q tests/test_mtf_checklist.py`.

## Task 3: Closed-candle API integration

- [x] Exclude a forming candle only from v2.
- [x] Preserve timeframe live-candle status and other checklist rows.
- [x] Verify: `uv run pytest -q tests/test_mtf_analysis_api.py`.

## Checkpoint: complete

- [x] `uv run pytest -q`.
- [x] Frontend lint, typecheck, tests and build pass.
- [x] Specification reflects the implemented contract.
- [x] No TradingView state was changed.
