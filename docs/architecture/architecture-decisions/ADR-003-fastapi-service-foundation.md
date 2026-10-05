# ADR-003: Python and FastAPI for the local MCP API service

## Status

Accepted for Phase 1B.

## Decision

Use Python and FastAPI for the local, read-only MCP API service.

## Rationale

- Python is well suited to OHLCV processing, technical-indicator calculations, and deterministic rule evaluation planned for later phases.
- FastAPI provides typed contracts, generated local API documentation, and asynchronous endpoints for the future official-MCP adapter.
- The service keeps source-specific implementation behind a provider boundary, allowing the official MCP to remain primary and the Desktop bridge to remain a future fallback.

## Security boundary

The service does not read, copy, or depend on the Codex desktop OAuth credential store. It will obtain and retain its own OAuth credentials through an explicitly designed local authorization flow in a later connector task.
