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

## Task 9: Desktop watchlist quote capability gate

**Description:** Confirm the existing bridge can read quote rows from the
active `PS_Global_Indices` watchlist without changing the chart or watchlist.

**Acceptance criteria:**

- [x] Arbitrary-symbol OHLCV requires active chart switching and is not used.
- [x] Live Desktop watchlist rows match the exact approved 30-symbol sequence.
- [x] A live read did not change the active chart (`NSEIX:NIFTY1!`, daily).
- [x] Official OHLCV samples have valid OHLC fields with `v: null`; this was
  the cause of the backend validation error.

**Verification:**

- [x] Run the TradingView Desktop readiness probe after restart; CDP is
  reachable and the bridge reports `api_available: true`.
- [x] Record result in
  `docs/validation/desktop-ohlcv-fallback-capability.md`.

**Dependencies:** Approved Desktop-fallback specification.

**Files likely touched:**

- `docs/validation/desktop-ohlcv-fallback-capability.md`

**Estimated scope:** Small (1 file)

## Checkpoint: Desktop quote fallback capability

- [x] Current bridge does not provide symbol-addressable Desktop OHLCV.
- [x] User selected the visible-watchlist quote fallback.
- [x] No chart, pane, layout, or watchlist mutation occurred.

## Task 10: Desktop watchlist quote reader

**Description:** Normalize visible Desktop watchlist quote rows behind a
read-only adapter with an exact approved-symbol-sequence check.

**Acceptance criteria:**

- [x] Price and percentage fields are parsed and source attribution is kept.
- [x] Missing change percentage retains the price and remains unavailable for
  breadth.
- [x] Only the `watchlist get` read command is invoked.

**Verification:**

- [x] Focused tests pass: `uv run pytest -q tests/test_desktop_bridge.py`.
- [x] Full backend suite passes: `uv run pytest -q`.

**Dependencies:** Task 9.

**Estimated scope:** Medium (3 files)

## Task 11: Official-first Global Market quote fallback

**Description:** Use a Desktop watchlist quote only after official MCP evidence
fails and expose the selected evidence source to the dashboard.

**Acceptance criteria:**

- [x] Official valid evidence bypasses Desktop.
- [x] Official failure makes one Desktop fallback attempt per snapshot.
- [x] A Desktop row with no percentage remains unavailable and excluded from
  breadth.

**Verification:**

- [x] Focused tests pass: `uv run pytest -q tests/test_global_market_live.py`.
- [x] Full backend suite plus frontend lint/typecheck/build/tests pass.
- [x] Live read-only check confirms active chart and watchlist are unchanged.

**Dependencies:** Task 10.

**Estimated scope:** Medium (up to 5 files)

## Task 12: Configure the local Desktop bridge fallback

**Description:** Add a safe local environment-file workflow for the existing read-only bridge and document how the backend loads that configuration on startup.

**Acceptance criteria:**

- [x] The machine-specific CLI path is stored only in ignored `.env.local`; tracked files contain a placeholder, not a personal path or credential.
- [x] The documented backend startup command loads `.env.local` and preserves the existing official-first provider order.
- [x] Existing tests protect the read-only CLI contract and Official-first Desktop fallback behavior.

**Verification:**

- [x] `uv run --env-file .env.local pytest -q tests/test_desktop_bridge.py tests/test_global_market_live.py`

**Dependencies:** Task 11 and a healthy read-only Desktop bridge.

**Files likely touched:**

- `.env.example`
- `README.md`
- `docs/operations/tradingview-connection-runbook.md`

**Estimated scope:** Medium (4 files plus ignored local config)

## Task 13: Verify runtime failover end to end

**Description:** Restart the local backend with the bridge configuration and verify the Global Market API falls back to Desktop when Official MCP cannot provide evidence.

**Acceptance criteria:**

- [x] Desktop quote evidence is labeled `desktop_bridge` with a local observation time.
- [x] Missing percentage values retain a price only when available and remain excluded from breadth; invalid watchlists are rejected.
- [x] Active chart and watchlist are unchanged by the read-only fallback.

**Verification:**

- [x] `/health` and the Global Market endpoint respond after startup.
- [x] Live response is checked for the exact approved 30-symbol sequence and source/freshness attribution.
- [x] Backend started with the documented command for live verification and
  was stopped afterward at the user's request.

**Dependencies:** Task 12.

**Files likely touched:**

- `docs/validation/desktop-ohlcv-fallback-capability.md`
- Local runtime; no application logic change expected.

**Estimated scope:** Small (runtime verification only)

## Task 14: Prepare the TradingView bridge before backend startup

**Description:** Provide one macOS command that ensures TradingView Desktop is
available over its required CDP port, waits for the bridge API, validates the
active watchlist, and then starts the local backend.

**Acceptance criteria:**

- [x] Reuse a healthy TradingView CDP session on port 9222.
- [x] If CDP is absent, request a graceful app quit and relaunch with port 9222;
  never force-kill TradingView.
- [x] Wait for the bridge chart API before starting the backend.
- [x] Compare the active watchlist against the approved ordered symbols and
  warn when it differs, without changing watchlist selection or contents.
- [x] Official MCP remains usable if Desktop fallback is unavailable.

**Verification:**

- [x] `bash -n scripts/start-local.sh`
- [x] Focused fallback tests pass.
- [x] Live script run confirms healthy-bridge reuse and exact active-watchlist
  validation; the Global Market API returned all 30 items from `desktop_bridge`.
- [x] Full backend suite passes.

**Dependencies:** Task 13.

**Estimated scope:** Small (startup helper and operational documentation)
