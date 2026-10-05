# Specification: setup scoring and status

## Rule categories

- **Mandatory:** must pass for `Near ready` or `Confirmed`.
- **Weighted optional:** contributes to readiness percentage but cannot override mandatory failures.
- **Informational:** displayed as context but does not affect status.
- **Invalidation:** immediately changes the state to `Invalidated`.

## Readiness calculation

```text
weighted completion = passed optional weight / evaluable optional weight × 100
```

Unavailable optional rules are excluded only when the specification explicitly permits it. Otherwise, data is incomplete and the setup cannot be confirmed.

## Default state policy

| Condition | Status |
| --- | --- |
| Critical context unavailable/stale | Data unavailable |
| Any invalidation rule passes | Invalidated |
| Mandatory rule fails | Not ready |
| Mandatory rules pass; score below near-ready threshold | Developing |
| Mandatory rules pass; score at/above near-ready threshold | Near ready |
| Mandatory rules and entry confirmation pass; score at/above confirmed threshold | Confirmed |

Thresholds are setup-specific and must be written in each setup specification.
