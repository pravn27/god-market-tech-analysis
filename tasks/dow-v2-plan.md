# Implementation Plan: Dow Structure v2

## Overview

Implement the approved additive Dow v2 checklist evidence while preserving the
existing v1 row and screen decisions.

## Architecture decisions

- Pure swing normalization and classification stay in `price_structure.py`.
- Checklist mapping stays in `mtf_checklist.py`.
- `mtf_analysis.py` determines whether the latest candle is live and passes
  that fact to checklist evaluation.
- Existing API shapes remain compatible; the new checklist row is additive.
- TradingView remains read-only and is used only as a documented validation
  reference.

## Dependency graph

```text
Pure v2 swing model and tests
    -> checklist row and evidence mapping
        -> live-candle exclusion plumbing
            -> API/frontend regression verification
```

## Task list

1. Pure v2 structure: alternating normalization, classification, break evidence
   and ATR significance.
2. Add the v2 checklist row and closed-candle evaluation contract.
3. Pass live-candle state from the analysis service and verify API compatibility.
4. Run focused/full backend and frontend quality gates; update documentation.

## Risks and mitigations

- Same-bar high/low has unknown intrabar order: omit and disclose it.
- Additive row could affect fixture assumptions: update only tests that
  intentionally enumerate rows.
- A live-candle exclusion could leak into v1: keep separate candle inputs and
  add an API regression test.

## Checkpoints

- After Task 1: focused price-structure tests pass.
- After Tasks 2-3: checklist and API tests pass.
- Complete: backend suite and frontend lint/typecheck/tests/build pass.
