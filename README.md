# God Market Technical Analysis

This repository is the home for the God Market technical-analysis workflow, its specifications, and the future local decision-support application.

## Scope

- Define the multi-timeframe analysis process and manual decision workflow.
- Document indicators, checklist criteria, trade-setup rules, and invalidation logic.
- Record the local TradingView MCP integration, dashboard, monitoring, alerts, and operating runbooks.
- Use specification-driven development and verification evidence before feature implementation.

## Status

The repository is in Phase 0: the documentation-first foundation. No dashboard, market-data connector, broker integration, or trading automation is implemented.

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

Start with the [documentation map](docs/README.md), then review the [high-level design](docs/architecture/high-level-design.md) and [delivery model](docs/delivery/github-project-model.md).

The high-level design follows the reference flow in `docs/reference-img/high-level-design-flow.png`: Client Side Web App → Business Logic Backend Service → MCP API Service → TradingView MCP → TradingView Desktop App. The design also records the reverse chart-context path and the separate local WebSocket path used to update the dashboard.

## Contributing

Keep changes focused, document assumptions behind analysis rules, and avoid treating technical-analysis output as financial advice.
