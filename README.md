# God Market Technical Analysis

This repository is the home for the God Market technical-analysis workflow, its specifications, and the future local decision-support application.

## Scope

- Define the multi-timeframe analysis process and manual decision workflow.
- Document indicators, checklist criteria, trade-setup rules, and invalidation logic.
- Record the local TradingView MCP integration, dashboard, monitoring, alerts, and operating runbooks.
- Use specification-driven development and verification evidence before feature implementation.

## Status

The repository is in Phase 1D: the local read-only MCP API service is authorized against the official TradingView MCP and has passed a live, read-only OHLCV validation. It normalizes source-attributed `ChartContext` and clearly flags a temporarily unavailable technical snapshot rather than fabricating one.

## Structure

```text
docs/
├── product/          Product scope, workflows, and feature catalogue
├── architecture/     High- and low-level design plus architecture decisions
├── specifications/   Testable MTF, setup, scoring, and notification behaviour
├── validation/       Acceptance criteria, tests, and chart verification
├── operations/       Local connection, privacy, and recovery runbooks
├── knowledge-base/   Stable methodology definitions
└── delivery/         GitHub Projects model and release evidence
```

## Local API service

Requires Python 3.10 or newer. The project uses the official MCP Python SDK, which does not support Python 3.9.

```bash
uv sync --group dev
uv run uvicorn god_market_api.app:app --reload --no-access-log
```

The API is local-only. Visit `http://127.0.0.1:8000/docs` for its generated API documentation.

- `GET /health` reports source readiness.
- `GET /api/v1/chart-context/{symbol}?timeframe=1h` returns a normalized chart context when an authenticated provider is configured.
- `GET /api/v1/multi-timeframe-context/{symbol}` returns the assembled Monthly, Weekly, Daily, 4H, 1H, and 15m context for the future Confluence Board. Repeat `timeframe` to request a typed subset, for example `?timeframe=daily&timeframe=4h`.
- The multi-timeframe endpoint returns `200` for complete or partial evidence and `503` with a typed unavailable result only when no requested timeframe is usable.
- `GET /api/v1/global-market-sentiment?timeframe=daily` returns ordered `PS_Global_Indices` groups and explicit breadth evidence for the Global Market dashboard. It uses official MCP two-candle OHLC evidence first and can use a validated, source-labelled Desktop watchlist quote for an unavailable item. A Desktop quote without change percentage remains excluded from breadth.
- Until the application-owned official-MCP OAuth authorization completes, chart-context requests safely return `503` rather than fabricated or stale data.
- A rate-limited technical snapshot produces an explicit warning while current OHLCV remains available.

## Local dashboard shell

The React dashboard is isolated in `frontend/`. It uses Ant Design's `PS ASTA Setup`-inspired dark theme and communicates with the local FastAPI API only.

```bash
cd frontend
npm install
npm run dev
```

Before a release, run `npm run test`, `npm run lint`, `npm run typecheck`, and `npm run build`. The first rendered feature is the Global Market view; it does not expose TradingView credentials or connect directly to TradingView.

## Official MCP authorization

The local service has its own OAuth flow and never reuses the Codex application's OAuth credentials. It stores its dynamically registered client information and refresh tokens in the local operating-system keyring.

1. Start the local API service.
2. Request `POST /api/v1/oauth/official/start`.
3. Review the returned authorization URL and open it only after the user approves the TradingView connection.
4. TradingView redirects to the local callback endpoint. The service exchanges the code, stores credentials in the keyring, and discovers read-only MCP tools. Start the local service with `--no-access-log` so authorization codes are never written to terminal access logs.

No OAuth interaction begins merely by starting the service.

Start with the [documentation map](docs/README.md), then review the [high-level design](docs/architecture/high-level-design.md) and [delivery model](docs/delivery/github-project-model.md).

The high-level design follows the reference flow in `docs/reference-img/high-level-design-flow.png`: Client Side Web App → Business Logic Backend Service → MCP API Service → TradingView MCP → TradingView Desktop App. The design also records the reverse chart-context path and the separate local WebSocket path used to update the dashboard.

## Contributing

Keep changes focused, document assumptions behind analysis rules, and avoid treating technical-analysis output as financial advice.
