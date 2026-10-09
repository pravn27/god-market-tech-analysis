# Product delivery roadmap

## Reference experience

The existing [Stock Market TA global-market page](https://pravn27.github.io/stock-market-tech-analysis/global-market) is a **presentation and interaction reference** for God Market. Its useful patterns are grouped views, compact multi-timeframe summary cards, selectable timeframe detail, refresh controls, table/card views, and clear loading or error states.

God Market does not copy its implementation. The reference application uses a separate yfinance-based service and market-breadth sentiment calculations. God Market uses its application-owned TradingView MCP connection, preserves source and freshness evidence, and adds the user's multi-timeframe checklist and setup rules.

## Epics, features, and stories

| Epic | Features | First stories | Status |
| --- | --- | --- | --- |
| E-01 Local platform foundation | Project layout, typed API, test harness, local developer workflow | Create the FastAPI service; define source-attributed contracts; establish tests | Done |
| E-02 TradingView source integration | Official MCP OAuth, normalized OHLCV adapter, source health | Authorize the local client; retrieve OHLCV; handle unavailable and rate-limited responses | Done |
| E-03 Multi-timeframe context | MTF orchestrator, freshness policy, cache and request budget | Define the MTF response; fetch one symbol across six timeframes; return partial-data evidence | Done |
| E-04 Technical enrichment | Local indicator series, price structure, support/resistance evidence | Calculate indicator inputs from OHLCV; classify trend and location; retain raw evidence | Done (profile `mtf-checklist-v1`) |
| E-05 Market context | Optional global/sector/commodity context panels patterned after the reference dashboard | Define market groups; collect read-only context; display source-attributed breadth/context | Global Market slice done |
| E-06 Confluence Board dashboard | Super TIDE → Ripple board, timeframe selector, detail drill-down | Render six context cards; show source/freshness; open a timeframe evidence panel | Multi-Timeframe checklist slice done |
| E-07 Rule-engine foundation | Deterministic rules, mandatory/weighted outcomes, explanation contracts | Define pure rule interface; evaluate one rule; test failure and unavailable cases | Backlog |
| E-08 Setup registry | Versioned definitions for 10–12 named setups | Define setup schema; load one versioned setup; validate its rule references | Backlog |
| E-09 Checklist and setup detail | PAPA/SMM checklist view, passed/failed/pending evidence, manual decision record | Model checklist evidence; display one setup evaluation; record a manual decision | Checklist view done; setup evaluation and decision record pending |
| E-10 Readiness monitoring | Thresholds, state transitions, debounce and re-arm policy | Evaluate a setup on refresh; detect one transition; suppress repeated unchanged events | Backlog |
| E-11 Local history and audit | Evaluation history, configuration versions, chart-verification records | Persist evaluations locally; query history; retain rule and source versions | Backlog |
| E-12 Local live updates | Versioned WebSocket events and dashboard refresh coordination | Define an event envelope; push source/evaluation update; reconnect safely | Backlog |
| E-13 Notifications | In-dashboard notifications and optional Gmail delivery | Create local notification inbox; add state-change rules; add user-approved Gmail channel | Backlog |
| E-14 Configuration portability | Import/export, validation, macOS/Windows-compatible paths | Export non-secret configuration; validate import; never export keychain credentials | Backlog |
| E-15 Cross-platform release and operations | Packaging, local install/update/recovery runbooks, release evidence | Package for macOS and Windows; document recovery; run release acceptance checklist | Backlog |

## Delivery sequence

`E-03 → E-04 → E-06 → E-07 → E-08 → E-09 → E-10 → E-11 → E-12 → E-13 → E-14 → E-15`

E-05 may proceed after E-03 when global/sector context is needed; it must remain advisory context, not hidden trade logic.

## Next approved planning unit

**E-04 / Task 1 — Define indicator profile and evidence contracts.**

Its governing specification is [technical-enrichment.md](../specifications/technical-enrichment.md). No rule-engine or dashboard decision logic belongs in this task.

## Active priority adjustment

The Global Market Sentiment UI is being delivered as an approved E-05 vertical slice before E-04 implementation. It provides source-attributed market context and a reusable dashboard foundation; it does not depend on technical-enrichment or setup-rule conclusions.

The Multi-Timeframe page (2026-10-09) delivered E-04 together with vertical slices of E-06 and E-09: the PAPA + SMM checklist for one `PS_DailyWatch_Favourite` instrument across eight worksheet columns, with SMM Double / Triple Screen decisions. Governing specification: [mtf-analysis-checklist.md](../specifications/mtf-analysis-checklist.md). Indicator values were validated against the TradingView chart on 2026-10-09 (see that specification).
