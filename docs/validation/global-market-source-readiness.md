# Global Market source readiness — 2026-10-07

## Task 1 status

**Completed — read-only Desktop discovery.**

## Read-only pre-flight evidence

- TradingView Desktop was gracefully relaunched with the user's approval and CDP enabled on `127.0.0.1:9222`.
- The bridge attached successfully with chart API availability confirmed.
- Active chart: `TVC:DJI`, Daily.
- Layout list contains `PS ASTA Setup - black theme`; it is the active layout context.
- Active watchlist: `PS_Global_Indices`.

## Read-only `PS_Global_Indices` snapshot

The following order and symbols were read without mutation after the user manually maintained the watchlist. This is the approved dashboard universe:

| Section | Visible symbols |
| --- | --- |
| USA | `TVC:DJI`, `DJCFD:DJT`, `NASDAQ:NDX`, `CBOE:MAGS`, `NASDAQ:IXIC`, `VANTAGE:USDINR`, `TVC:SPX`, `BLACKBULL:DJ30.F`, `BLACKBULL:US30`, `TVC:NYA`, `CBOEFTSE:RUT`, `TVC:DXY`, `TVC:VIX` |
| EUROPE | `XETR:DAX`, `TVC:CAC40`, `FTSE:UKX` |
| ASIA PACIFIC | `NSEIX:NIFTY1!`, `TVC:HSI`, `TVC:NI225`, `TVC:STI`, `KRX:KOSPI`, `ASX:XJO`, `IDX:COMPOSITE`, `SET:SET`, `TWSE:TAIEX`, `SSE:000300` |
| INDIA ADRS | `NYSE:INFY`, `NYSE:WIT`, `NYSE:IBN`, `NYSE:HDB` |

`FXCM:EUSTX50` was considered but is intentionally excluded because the instrument was not available to the user. The dashboard never substitutes a different EURO STOXX 50 feed.

## Impact

No replacement universe was created. The user manually maintained the approved watchlist; the application only consumes the resulting read-only snapshot. No source, layout, indicator, drawing, or alert was changed by the application.

## Required recovery

Task 2 can now define the fixture and API response contracts from this snapshot. Coverage changes remain a separate dry-run and confirmation task.
