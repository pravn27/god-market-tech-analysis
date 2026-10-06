# Global Market dashboard — Task 5 validation

**Date:** 2026-10-06
**Scope:** Fixture-backed Daily Global Market vertical slice
**Environment:** Local FastAPI on `127.0.0.1:8000`, local Vite dashboard on `127.0.0.1:5173`

## Verified behaviour

- The `/global-market` route rendered the Daily Global Market dashboard through the Vite local-API proxy.
- The dashboard displayed the existing read-only watchlist section ordering: `USA`, `EUROPE`, `ASIA PACIFIC`, and `INDIA ADRS`.
- Daily breadth showed advancing, declining, unchanged, and unavailable counts.
- Fixture-only status and the reason unavailable entries are excluded from directional breadth were visible.
- Instrument rows displayed source-derived evidence fields, including direction, freshness, and the unavailable reason for `NYSE:INFY`.
- Selecting **Refresh** re-requested the local API and updated the local read timestamp.

## Safety boundary

The response was clearly marked as fixture data. The browser called only `/api/v1/global-market-sentiment` through localhost; it did not receive TradingView credentials or call TradingView directly. No TradingView watchlist or layout was changed.

## Automated evidence

- Backend: `uv run pytest -q` — 37 passed.
- Frontend: `npm run test` — 5 passed.
- Frontend: lint, type check, and production build passed.

The Vite production build reports an initial Ant Design bundle-size advisory. It is not a correctness failure; route-level code splitting can be considered as the application gains more screens.
