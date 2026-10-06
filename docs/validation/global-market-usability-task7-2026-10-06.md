# Global Market usability controls — Task 7 validation

**Date:** 2026-10-06
**Scope:** Local-only Global Market dashboard controls

## Result

- Section selector filters the already-received local snapshot; it does not call TradingView or alter `PS_Global_Indices`.
- Table and Cards present the same response data in two forms.
- `View evidence` opens a detail drawer with the selected instrument's source, freshness, observed time, price/change evidence, and any unavailable reason.
- A local browser check filtered to `INDIA ADRS`, selected Cards, and opened the Infosys ADR drawer. It correctly displayed the current official-MCP unavailable reason rather than inventing a value.

## Automated checks

- `npm run test`: 6 passing tests
- `npm run lint`: passed
- `npm run typecheck`: passed
- `npm run build`: passed (only the existing bundle-size advisory)

## Safety boundary

This task makes no TradingView MCP write, Desktop action, watchlist/layout change, alert, order, or browser-to-TradingView request.
