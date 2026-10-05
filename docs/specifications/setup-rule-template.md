# Trade setup specification template

Copy this file for every setup. Do not implement a setup from an informal description alone.

## Metadata

- Setup ID and name:
- Version:
- Owner/author:
- Purpose:
- Intended direction: bullish, bearish, or both:
- Last reviewed date:

## Preconditions

- Required symbols/markets:
- Required timeframes:
- Required source data:

## Rules

| ID | Rule | Timeframe | Type | Weight | Pass evidence | Fail / unavailable behaviour |
| --- | --- | --- | --- | ---: | --- | --- |
| R-01 | Example: Higher timeframe aligns with long bias | Weekly | Mandatory | N/A | HH-HL structure | Blocks confirmation |

## Scoring and status

- Mandatory conditions:
- Optional weighted conditions:
- Near-ready threshold:
- Confirmed threshold:
- Invalidation conditions:
- Alert suppression/re-arm conditions:

## Explanation format

State the passed, failed, pending, and unavailable rules separately. Include the evaluation timestamp and rule-set version.

## Acceptance scenarios

| Scenario | Input context | Expected result |
| --- | --- | --- |
| Valid setup | All mandatory rules pass; optional score reaches threshold | Correct readiness and evidence |
| Mandatory failure | Invalidation condition is true | `Invalidated` regardless of score |
| Missing data | One required timeframe is stale/unavailable | No confirmation; clear reason |
