# Test strategy

## Test layers

| Layer | Goal | Examples |
| --- | --- | --- |
| Unit | Verify deterministic calculations | trend classification, weighted score, invalidation precedence |
| Contract | Verify adapter output is valid internal context | missing timestamps, unsupported timeframes, malformed values |
| Integration | Verify component boundaries | adapter → rules engine → local event stream |
| UI | Verify visible decision support | stale-data badge, drill-down evidence, status ordering |
| Replay | Compare known historical scenarios | recorded candle/context fixture produces expected setup state |
| Manual chart verification | Confirm result against TradingView | selected chart, timeframe, timestamp, expected/actual outcome |

## Required edge cases

- Missing, delayed, and stale data.
- Conflicting higher and lower timeframe signals.
- A high weighted score with a failed mandatory rule.
- A confirmed setup becoming invalidated.
- MCP disconnection and reconnection.
- Repeated unchanged evaluations without duplicate notifications.

## Quality gate

No rule-set change is complete until its replay scenarios pass and at least one representative manual chart verification is recorded.
