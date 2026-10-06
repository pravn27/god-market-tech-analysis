# Global Market Sentiment UI — task checklist

## Task 1: Read-only TradingView Desktop discovery

**Description:** Verify the Desktop MCP bridge and inspect `PS_Global_Indices` plus the `PS ASTA Setup - black theme` layout context without changing either artifact.

**Acceptance criteria:**

- [x] Bridge/CDP readiness and active chart state are recorded, or the exact blocker is recorded.
- [x] `PS_Global_Indices` is read with its existing section names, order, and symbols preserved.
- [x] No watchlist, layout, indicator, or drawing mutation occurs.

**Verification:**

- [x] Run the TradingView session pre-flight.
- [x] Produce a read-only snapshot or blocker report.

**Dependencies:** None

**Files likely touched:**

- `docs/validation/global-market-source-readiness.md`

**Estimated scope:** Small (1 file)

## Task 2: Global Market contracts and fixtures

**Description:** Define backend response models for ordered watchlist groups, source-attributed item evidence, completeness, and breadth. Add fixture data that reflects existing watchlist sections without an external request.

**Acceptance criteria:**

- [x] Contract represents complete, partial, and unavailable evidence without a trade recommendation.
- [x] Group ordering is explicit and preserved.
- [x] Fixture data covers available and unavailable items.

**Verification:**

- [x] Tests pass: `uv run pytest -q tests/test_global_market_models.py`
- [x] Existing tests pass: `uv run pytest -q`

**Dependencies:** Task 1

**Files likely touched:**

- `src/god_market_api/models.py`
- `tests/test_global_market_models.py`
- `docs/specifications/global-market-sentiment.md`

**Estimated scope:** Small (3 files)

## Task 3: Fixture-backed Global Market API slice

**Description:** Implement a pure snapshot/breadth use case over fixture data and expose the additive localhost API endpoint.

**Acceptance criteria:**

- [x] Fixture data returns ordered groups and explicit breadth evidence.
- [x] Partial/unavailable items remain visible and are excluded from directional counts with an explanation.
- [x] Existing chart-context and MTF endpoints do not regress.

**Verification:**

- [x] Tests pass: `uv run pytest -q tests/test_global_market_api.py`
- [x] Existing tests pass: `uv run pytest -q`
- [x] Manual check: inspect the generated local OpenAPI contract.

**Dependencies:** Task 2

**Files likely touched:**

- `src/god_market_api/global_market.py`
- `src/god_market_api/app.py`
- `tests/test_global_market_api.py`

**Estimated scope:** Small (3 files)

## Task 4: React application and Ant Design theme shell

**Description:** Create the isolated TypeScript React/Vite application, Ant Design dark theme tokens, routing shell, local API client, and test/build tooling.

**Acceptance criteria:**

- [x] The frontend builds, type-checks, and renders a route shell locally.
- [x] Ant Design tokens provide the `PS ASTA Setup` black-theme foundation.
- [x] Frontend has no TradingView credentials, MCP connection, or direct source request.

**Verification:**

- [x] Frontend unit tests pass.
- [x] `npm run lint`, `npm run typecheck`, and `npm run build` pass in `frontend/`.

**Dependencies:** Task 3

**Files likely touched:**

- `frontend/package.json`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/theme.ts`
- `frontend/src/api/client.ts`

**Estimated scope:** Medium (5 files)

## Task 5: Daily Global Market dashboard vertical slice

**Description:** Render the fixture-backed local API response as Ant Design summary cards and grouped market tables with refresh, loading, empty, error, and partial-data states.

**Acceptance criteria:**

- [x] User can open the Global Market route and see Daily breadth plus ordered groups.
- [x] Source timestamp, freshness, and unavailable state are visible.
- [x] Refresh refetches only the local API and never reaches TradingView from the browser.

**Verification:**

- [x] Frontend component tests pass.
- [x] Backend tests and frontend lint/typecheck/build pass.
- [x] Manual check: fixture-backed dashboard works locally.

**Dependencies:** Tasks 3–4

**Files likely touched:**

- `frontend/src/features/global-market/GlobalMarketPage.tsx`
- `frontend/src/features/global-market/SentimentSummary.tsx`
- `frontend/src/features/global-market/MarketGroupTable.tsx`
- `frontend/src/features/global-market/useGlobalMarket.ts`
- `frontend/src/features/global-market/*.test.tsx`

**Estimated scope:** Medium (5 files)

## Checkpoint: source and contract

- [x] Tasks 1–2 are complete.
- [x] Backend tests pass.
- [x] Human approves the response contract before endpoint/UI implementation.

## Checkpoint: daily dashboard

- [x] Tasks 3–5 are complete.
- [x] Backend and frontend automated checks pass.
- [ ] Human approves the dashboard hierarchy and source-status treatment.

## Task 7: Global Market usability controls

**Description:** Add local-only section filtering, table/card presentation, and an evidence detail drawer to the existing Daily Global Market page.

**Acceptance criteria:**

- [x] User can limit the visible dashboard to one recorded `PS_Global_Indices` section without changing watchlist data.
- [x] User can switch between a detailed table and compact cards.
- [x] User can inspect an instrument's source, freshness, price evidence, and unavailable reason in a drawer.
- [x] The browser continues to call only the local FastAPI endpoint.

**Verification:**

- [x] Frontend component tests cover filtering, card view, and evidence details.
- [x] Frontend lint, typecheck, and production build pass.
- [x] Local browser check confirms the controls and drawer render against live API results.

**Files touched:**

- `frontend/src/features/global-market/GlobalMarketPage.tsx`
- `frontend/src/features/global-market/MarketGroupTable.tsx`
- `frontend/src/features/global-market/MarketGroupCards.tsx`
- `frontend/src/features/global-market/MarketInstrumentDetailDrawer.tsx`
- `frontend/src/features/global-market/GlobalMarketPage.test.tsx`

## Task 8: PS_Global_Indices coverage dry-run

**Description:** Compare the recorded read-only watchlist snapshot with a compact global-sentiment coverage checklist and prepare a non-mutating proposal.

**Status:** Approval-ready dry-run produced. TradingView Desktop MCP re-read the existing 16 symbols and validated exact add candidates through symbol search.

- [x] Preserved the exact existing section names, section order, and recorded symbols.
- [x] Identified coverage gaps and validated exact TradingView symbols without guessing prefixes.
- [x] Produced no add, delete, or reorder action.
- [ ] Obtain the user's confirmation for the exact add set before changing the watchlist.

See [coverage dry-run](../docs/validation/global-market-coverage-dry-run-2026-10-06.md).
