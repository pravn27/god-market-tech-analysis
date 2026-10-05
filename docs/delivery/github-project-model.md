# Delivery and GitHub Projects model

## Work hierarchy

```text
Epic → Feature → Story → Task
```

- **Epic:** a major outcome, such as MTF dashboard or monitoring.
- **Feature:** a visible capability, such as setup drill-down.
- **Story:** a small user outcome that can be accepted independently.
- **Task:** implementation, test, documentation, or design work supporting one story.

## Suggested GitHub Project fields

| Field | Values / use |
| --- | --- |
| Status | Backlog, Specifying, Ready, In progress, Validation, Done, Blocked |
| Type | Epic, Feature, Story, Task, Bug, Spike |
| Area | Product, Architecture, Rules, Adapter, Dashboard, Monitoring, Operations |
| Priority | Must, Should, Could |
| Specification | Link to the governing document |
| Validation evidence | Link to tests/chart-verification record |
| Target release | Local milestone/version |
| Risk | Low, Medium, High |

## Initial epics

1. Foundation and local developer workflow.
2. TradingView/MCP capability spike and adapter contract.
3. Multi-timeframe context and Confluence Board.
4. Rule engine and first documented setup.
5. Monitoring, history, and local notifications.
6. Cross-platform packaging and operating runbooks.

## Workflow rules

- A work item cannot move from `Specifying` to `Ready` without acceptance criteria.
- A work item cannot move to `Done` without validation evidence.
- `Blocked` requires the blocker and next decision to be written on the item.
- Keep implementation branches short-lived and scoped to one reviewable story.

## Suggested release evidence

For each local release, record included stories, validation results, known limitations, connection prerequisites, and rollback steps.

## Current delivery checkpoint

Phase 1C adds a contract-tested adapter that maps official-MCP OHLCV and single-timeframe technical responses into `ChartContext`. It does not evaluate rules or synthesize trade signals. The next story validates an explicitly authorized live connection and records source freshness before any rule calculation or dashboard work depends on it.
