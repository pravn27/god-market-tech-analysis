# Official TradingView MCP capability matrix

## Verification record

- Date: 2026-10-05
- Connector: Official TradingView MCP at `https://mcp.tradingview.com/mcp`
- Authentication: OAuth 2.1 completed successfully
- Scope: read-only capability discovery; no chart, watchlist, alert, or Desktop-bridge mutation

## Verified capabilities

| Need | Official MCP capability | Design implication |
| --- | --- | --- |
| Resolve a trading symbol | Symbol search returns routable `EXCHANGE:TICKER` symbols | The symbol configuration must persist the resolved exchange-qualified symbol. |
| Quotes and screener fields | Single-symbol and batch symbol data; batch limit is 50 symbols | The monitor must batch requests and treat missing symbols as unavailable, never as zero. |
| Candle history | OHLCV is available with fixed intervals and up to 5,000 bars | The backend can calculate historical indicators and chart structure from normalized OHLCV. |
| Technical snapshot | Detailed technical rating is available for one timeframe per call, from 1 minute to 1 month | MTF Confluence Board must request/evaluate each timeframe separately. The adapter maps the OHLCV monthly code `M` to the technicals-tool monthly code `1M`. |
| MTF aggregate | No dedicated MTF aggregate tool was found | The rules engine, not the connector, combines timeframe results. |
| Historical indicator series | No dedicated indicator-history tool was found | Calculate RSI, MACD, DMI/ADX, EMAs, Bollinger Bands, and Stochastic from OHLCV in the rules layer. |
| Watchlist reads | List and retrieve owned or public shared watchlists | Use explicit read-only list/get operations. Do not call active-watchlist operations without confirming their behaviour. |
| Alert reads | List alerts, retrieve alerts, and retrieve alert logs | Alert logs default to seven days and support at most 2,000 events. Alert payloads intentionally omit message and webhook URL. |
| Other context | News, financials, forecasts, economic data/calendars, dividends, earnings, and screeners | These are optional later enrichments, not prerequisites for the initial MTF dashboard. |

## Constraints

- The connector is accessed through tool calls, not a documented direct streaming-price WebSocket.
- The local backend remains responsible for its own WebSocket stream to the dashboard.
- The monitor must use controlled refresh/candle-close scheduling, caching, and rate-limit-aware batching.
- Every `ChartContext` includes the source ID, source timestamp, and freshness status.

## Initial suitability decision

The official MCP is suitable as the primary source for the first read-only multi-timeframe decision-support system. Its required data will be normalized by the MCP API service, and all multi-timeframe comparison plus indicator-history calculation will occur in the local rules engine.

The Desktop/CDP bridge remains an untested fallback. It must be validated independently before it can be selected automatically during an official-MCP outage or capability gap.
