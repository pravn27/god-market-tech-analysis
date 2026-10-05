# High-level design

## System boundary

The system runs only on the user's Mac or Windows machine. Its primary request path deliberately follows the supplied `high-level-design-flow.png`:

```text
Client Side Web App → Business Logic Backend Service → MCP API Service
→ TradingView MCP → TradingView Desktop App
```

The official TradingView MCP (`https://mcp.tradingview.com/mcp`) is the primary source. The existing local TradingView Desktop/CDP bridge is the fallback source. The local backend owns rule evaluation and supplies WebSocket updates to the local browser dashboard.

```mermaid
flowchart LR
    UI[Client Side Web App\nlocal dashboard] --> CORE[Business Logic Backend Service\nAPI, orchestration and rules]
    CORE --> MCPAPI[MCP API Service\nsource-neutral adapter]
    MCPAPI --> OFFICIAL[Official TradingView MCP\nPrimary · OAuth 2.1]
    MCPAPI -. fallback only .-> LOCAL[Existing local TradingView MCP bridge\nDesktop/CDP]
    LOCAL --> TV[TradingView Desktop App\nbackup path]

    OFFICIAL -. supported MCP response .-> MCPAPI
    TV -. available chart context .-> LOCAL
    LOCAL -. normalized response/event .-> MCPAPI
    MCPAPI -. ChartContext .-> CORE
    CORE --> RULES[Rules engine\nMTF and setup evaluation]
    RULES --> STORE[(Local configuration\nand history store)]
    RULES --> MONITOR[Monitoring and\nstate transitions]
    CORE --> WS[Local WebSocket server]
    WS -. live dashboard update .-> UI
    MONITOR -. state / alert event .-> UI
    MONITOR --> NOTIFY[Local alert service\noptional Gmail]
```

## Request path versus update path

| Path | Direction | Meaning |
| --- | --- | --- |
| Primary request path | Dashboard → Backend → MCP API service → Official TradingView MCP | Uses the official OAuth-authenticated MCP for supported data and platform operations. |
| Backup request path | Dashboard → Backend → MCP API service → Local TradingView MCP bridge → TradingView Desktop | Used only when the primary source is unavailable or cannot provide the required capability. |
| Chart-context response path | Official MCP or Desktop bridge → MCP API service → Backend | Returns only the context supported by the active source. |
| Dashboard live-update path | Backend → local WebSocket → Dashboard | Streams evaluated setup state, health, and notification events to the browser. |

The dashboard WebSocket is therefore a **local backend-to-dashboard connection**. It is not described as a direct unsupported connection to TradingView's internal chart WebSocket.

## Component responsibilities

| Component | Responsibility | Must not do |
| --- | --- | --- |
| Client Side Web App | Present current state, evidence, health, and manual decisions | Calculate hidden trade logic or place orders |
| Business Logic Backend Service | Coordinate requests, configuration, rule evaluation, local APIs, and WebSocket events | Depend on a public cloud service |
| MCP API Service | Prefer official MCP; use the Desktop bridge only as fallback; translate either response into a stable internal chart-context model | Pretend unavailable data is current or silently switch sources |
| Rules engine | Evaluate deterministic MTF and setup rules | Fetch data or manage UI concerns |
| Monitor | Detect state changes, debounce alerts, keep audit history | Repeat identical notifications continuously |
| Local store | Persist configurations, rule versions, history, and manual decisions | Store TradingView passwords or secrets in source control |

## Architecture constraints

- Bind browser-facing services to `localhost` by default.
- Treat both MCP integrations as capabilities that must be validated by an early technical spike.
- Keep TradingView-specific details inside the adapter so the rules engine can be tested with recorded contexts.
- Do not use direct undocumented TradingView chart WebSocket protocols as a product dependency.
- Display the active data source and source timestamp in the dashboard and evaluation history.
