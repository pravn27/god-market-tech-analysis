# Global Market live read validation — 2026-10-06

**Scope:** Task 6 — read-only official TradingView MCP price integration
**Watchlist universe:** recorded `PS_Global_Indices` Desktop snapshot
**Timeframe:** Daily

## Source readiness

- Local application OAuth status: connected.
- Official MCP tool inventory: 35 read-only tools.
- A read-only Daily OHLCV request for `NSE:NIFTY` succeeded before the watchlist validation.

## Live snapshot outcome

The local `GET /api/v1/global-market-sentiment?timeframe=daily` endpoint used the official MCP as its only price/OHLCV source. It completed as **partial** rather than fabricating values:

- 16 approved watchlist instruments were attempted with a concurrency cap of six.
- Usable Daily OHLCV coverage varied across adjacent validation reads. One read returned usable USA evidence for `NASDAQ:NDX`, `CBOE:MAGS`, `VANTAGE:USDINR`, `BLACKBULL:DJ30.F`, and `BLACKBULL:US30`; another also returned evidence for all four India ADRs.
- Some symbols returned explicit unavailable evidence because the official MCP rejected the request or supplied an invalid candle. Those items were excluded from directional breadth and remained visible with their reason.
- `EUROPE` and `ASIA PACIFIC` remained empty because the approved Desktop watchlist snapshot contained no rows in those sections.

The exact available/unavailable mix can vary between reads as the official MCP accepts or rejects individual symbols. The dashboard preserves that partial state and never substitutes Desktop price data.

## Read behaviour

- Each Global Market item requests only two OHLCV candles—enough to calculate last price and Daily percentage change.
- The Global Market path does not request technical ratings and does not issue any write, chart, layout, watchlist, order, or alert action.
- The browser calls only the local FastAPI endpoint through the Vite localhost proxy.

## Follow-up

Symbol mapping/coverage review remains a separate dry-run task. No add, delete, reorder, or silent fallback is authorized by this validation.
