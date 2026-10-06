# Global Market source readiness — 2026-10-06

## Task 1 status

**Completed — read-only Desktop discovery.**

## Read-only pre-flight evidence

- TradingView Desktop was gracefully relaunched with the user's approval and CDP enabled on `127.0.0.1:9222`.
- The bridge attached successfully with chart API availability confirmed.
- Active chart: `TVC:DJI`, Daily.
- Layout list contains `PS ASTA Setup - black theme`; it is the active layout context.
- Active watchlist: `PS_Global_Indices`.

## Read-only `PS_Global_Indices` snapshot

The following order and symbols were read without mutation:

| Section | Visible symbols |
| --- | --- |
| USA | `TVC:DJI`, `DJCFD:DJT`, `NASDAQ:NDX`, `CBOE:MAGS`, `NASDAQ:IXIC`, `VANTAGE:USDINR`, `TVC:SPX`, `BLACKBULL:DJ30.F`, `BLACKBULL:US30`, `TVC:NYA`, `TVC:DXY`, `TVC:VIX` |
| EUROPE | No visible instrument rows |
| ASIA PACIFIC | No visible instrument rows |
| INDIA ADRS | `NYSE:INFY`, `NYSE:WIT`, `NYSE:IBN`, `NYSE:HDB` |

Europe and Asia Pacific are recorded as watchlist coverage gaps for the later dry-run. They are not automatically populated or otherwise modified.

## Impact

No replacement universe was created, and no source, layout, watchlist, indicator, drawing, or alert was changed.

## Required recovery

Task 2 can now define the fixture and API response contracts from this snapshot. Coverage changes remain a separate dry-run and confirmation task.
