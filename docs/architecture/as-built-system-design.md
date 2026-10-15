# As-built system design (HLD and LLD)

Status: describes the code as it runs on 2026-10-13 (Multi-Timeframe checklist on `PS_Commodity`, Global Market dashboard, official MCP OAuth, Desktop fallback).

Use this document to see the complete flow. The [high-level design](high-level-design.md) and [low-level design](low-level-design.md) describe the **target** architecture (WebSocket, rules engine, local store, monitor). Sections below mark what exists today and what is still planned.

Open the Markdown preview (`Cmd+Shift+V`) to render the diagrams. PNG renders of each Mermaid diagram are in [diagrams/](diagrams/). The Mermaid blocks are the source of truth, so regenerate the PNGs after editing them.

---

## Part 1 - High-level design (HLD)

### 1.1 System context

```mermaid
flowchart LR
    USER["Trader<br/>(local browser)"]

    subgraph LOCAL["Local Mac - localhost only"]
        direction TB
        SPA["React SPA<br/>Vite dev server :5173<br/>/global-market, /multi-timeframe"]
        API["FastAPI backend :8000<br/>uvicorn --reload --no-access-log"]
        SNAP[("data/mtf_watchlist.json<br/>PS_Commodity snapshot")]
        ENV[(".env.local<br/>bridge CLI path")]
        KC[("macOS Keychain<br/>OAuth tokens")]
        SYNC["scripts/sync-mtf-watchlist.mjs<br/>offline, read-only"]
        START["scripts/start-local.sh"]
    end

    subgraph TV_LOCAL["TradingView Desktop (local)"]
        DESK["TradingView Desktop app<br/>CDP port 9222"]
        BRIDGE["Desktop bridge CLI<br/>watchlist get, read-only"]
    end

    MCP["Official TradingView MCP<br/>mcp.tradingview.com/mcp<br/>OAuth 2.1 + PKCE"]

    USER --> SPA
    SPA -- "/api/v1 (Vite proxy)" --> API
    API -- "OHLCV, technicals<br/>(primary)" --> MCP
    API -- "watchlist quotes<br/>(fallback only)" --> BRIDGE
    BRIDGE --> DESK
    API -- "tokens" --> KC
    API -- "reads at start" --> SNAP
    API -- "reads bridge path" --> ENV
    START -- "graceful quit and relaunch<br/>then uvicorn" --> API
    START -- "chart API check" --> DESK
    SYNC -- "custom-list endpoint over CDP" --> DESK
    SYNC -- "writes snapshot (not dry-run)" --> SNAP
```

### 1.2 Layers

| Layer | Location | Responsibility | Built today |
| --- | --- | --- | --- |
| Presentation | `frontend/src/features/*`, `App.tsx` | Two pages: Global Market and Multi-Timeframe checklist | Yes |
| API | `src/god_market_api/app.py` | FastAPI routes, Pydantic response models, error mapping | Yes |
| Use cases | `mtf_analysis.py`, `global_market.py` | Load snapshot, orchestrate fetches, evaluate, build responses | Yes |
| Analysis engine | `technical_indicators.py`, `price_structure.py`, `mtf_checklist.py`, `mtf_screens.py` | Pure functions: indicators, Dow Theory, checklist cells, Double and Triple Screen | Yes |
| Orchestration and cache | `mtf_orchestrator.py`, `mtf_cache.py`, `mtf_policy.py` | Concurrency limit, in-flight deduplication, in-memory cache, freshness policy | Yes |
| Data adapters | `providers.py`, `oauth.py`, `desktop_bridge.py` | Official MCP client, OAuth token handling, Desktop CDP reader | Yes |
| Storage | `data/mtf_watchlist.json`, OS keychain, browser `localStorage` | Watchlist snapshot, credentials, theme preference | Yes |
| Realtime push, rules persistence, monitoring, alerts | none | Planned in the target design (epics E-07 to E-13) | No |

### 1.3 Source policy

| Data need | Primary | Fallback | Behaviour when both fail |
| --- | --- | --- | --- |
| Multi-Timeframe candles (6 timeframes) | Official MCP `mcp-tv-get-ohlcv` | None | Timeframe is `UNAVAILABLE` with a reason; the screen reports `INCOMPLETE — <tf> unavailable` |
| Global Market prices | Official MCP two-candle OHLC | Desktop watchlist quote, only for items the official source could not price | Item stays `UNAVAILABLE`; a warning names the Desktop failure |
| Watchlist membership (`PS_Commodity`, `PS_Global_Indices`) | Read-only Desktop read by the sync script or `start-local.sh` | Snapshot JSON on disk | Backend refuses symbols outside the snapshot (`422`) |

The backend never changes TradingView charts, watchlists or layouts.

### 1.4 Gaps between target and as-built

| Target design item | As-built status |
| --- | --- |
| WebSocket live updates to the dashboard | Built for the multi-timeframe checklist only (`/api/v1/mtf-analysis/{symbol}/live`, protocol v1; see [checklist spec](../specifications/mtf-analysis-checklist.md#live-updates-websocket-protocol-v1)). Global Market still uses TanStack Query. Rule-evaluation events are not built. |
| Local configuration and history store (SQLite or similar) | Not built. Cache is in memory and resets on restart. |
| Generic setup rules engine and setup status machine (`Data unavailable` to `Confirmed`) | Not built. The checklist and screens are fixed rules for the SMM method. |
| Monitor, state transitions, alert debounce | Not built. |
| Gmail or local notifications | Not built. |
| 1H validation against TradingView charts | Pending. The chart timeframe cannot be changed read-only. |

---

## Part 2 - Runtime flows

### 2.1 Start-up

```mermaid
flowchart TD
    A["./scripts/start-local.sh"] --> B{"Bridge already reachable<br/>on CDP 9222?"}
    B -- yes --> D["Reuse TradingView Desktop"]
    B -- no --> C{"TradingView running<br/>without CDP?"}
    C -- yes --> C1["Graceful quit<br/>(no force close)"] --> C2["Relaunch with CDP 9222"]
    C -- no --> C2
    C2 --> E["Wait for chart API"]
    D --> E
    E --> F{"Active watchlist =<br/>PS_Global_Indices?"}
    F -- no --> W["Print warning:<br/>Desktop fallback not accepted"]
    F -- yes --> G["Continue"]
    W --> H["uv run uvicorn god_market_api.app:app --reload"]
    G --> H
    H --> I["create_app()<br/>load snapshot, build services"]
```

`MultiTimeframeAnalysisService` loads `data/mtf_watchlist.json` in its constructor. A missing or invalid snapshot stops the backend at start-up.

### 2.2 Multi-Timeframe analysis (`GET /api/v1/mtf-analysis/{symbol}`)

```mermaid
sequenceDiagram
    autonumber
    participant UI as React MTF page
    participant API as FastAPI app.py
    participant SVC as MultiTimeframeAnalysisService
    participant ORC as MultiTimeframeContextOrchestrator
    participant C as LocalContextCache
    participant P as OfficialMCPProvider
    participant MCP as Official TradingView MCP
    participant CL as mtf_checklist + mtf_screens

    UI->>API: GET /mtf-analysis/PEPPERSTONE:NATGAS?refresh_mode=prefer_cache
    API->>SVC: analyze(symbol, force_refresh)
    SVC->>SVC: symbol in snapshot? else UnknownInstrumentError -> 422
    SVC->>ORC: get_context(symbol, 6 timeframes)
    loop each timeframe (at most 3 provider calls at once)
        ORC->>C: get(source, symbol, tf)
        alt FRESH or STALE cache hit
            C-->>ORC: context (READY or STALE)
        else miss or EXPIRED
            ORC->>ORC: join in-flight task or create one
            ORC->>P: get_chart_context(symbol, tf)
            P->>MCP: mcp-tv-get-ohlcv (count 500)
            MCP-->>P: candles
            P-->>ORC: ChartContext
            ORC->>C: put(context)
        end
    end
    ORC-->>SVC: MultiTimeframeContext (complete, partial or unavailable)
    opt any timeframe STALE
        SVC->>ORC: get_context(stale timeframes, force_refresh)
        ORC-->>SVC: replace only successful refreshes
    end
    loop each timeframe
        SVC->>CL: evaluate_timeframe(candles) -> indicators, checklist rows, Dow trend
    end
    SVC->>CL: evaluate_screens -> 4 layers, 3 double screens, 1 triple screen
    SVC-->>API: MultiTimeframeAnalysis
    API-->>UI: 200 JSON (completeness, timeframes, rows, layers, decisions, warnings)
```

Response codes: `200` for every analysis that passes the snapshot check, including `completeness: UNAVAILABLE` when no timeframe is usable (the screens then report `INCOMPLETE`). `422` is returned for a symbol outside the snapshot.

### 2.3 Global Market snapshot (`GET /api/v1/global-market-sentiment`)

```mermaid
sequenceDiagram
    autonumber
    participant UI as React Global Market page
    participant API as FastAPI app.py
    participant GM as GlobalMarketLiveSnapshotProvider
    participant OMCP as OfficialMCPProvider
    participant DESK as TradingViewDesktopWatchlistReader

    UI->>API: GET /global-market-sentiment?timeframe=daily
    API->>GM: get_snapshot(timeframe)
    alt snapshot cached less than 60 s
        GM-->>API: cached snapshot
    else refresh
        GM->>DESK: start read of PS_Global_Indices in parallel
        GM->>OMCP: two-candle OHLC per item (6 concurrent, 1 retry, 20 s budget, stop after 3 failures)
        OMCP-->>GM: prices or UNAVAILABLE per item
        alt some items unavailable and Desktop read succeeded
            GM->>GM: fill only unavailable items from Desktop quotes (source = desktop_bridge)
        else Desktop read failed
            GM->>GM: add warning "Desktop fallback was unavailable"
        end
        GM->>GM: calculate_breadth (desktop quotes without change % stay excluded)
    end
    GM-->>API: GlobalMarketSnapshot
    API-->>UI: 200 JSON (groups, items, breadth, desktop_fallback, warnings)
```

### 2.4 Official MCP OAuth (`/api/v1/oauth/official/*`)

```mermaid
sequenceDiagram
    autonumber
    participant UI as User / browser
    participant API as FastAPI oauth routes
    participant CO as OfficialMCPOAuthCoordinator
    participant KC as KeyringTokenStorage (macOS Keychain)
    participant AS as TradingView OAuth server

    UI->>API: GET /oauth/official/status
    API-->>UI: state (no tokens, no URLs in logs)
    UI->>API: POST /oauth/official/start
    API->>CO: create PKCE verifier, state, redirect 127.0.0.1:8000/callback
    CO-->>UI: authorization URL (shown to the user, never logged)
    UI->>AS: user approves in browser
    AS-->>API: GET /oauth/official/callback?code&state
    API->>CO: validate state, exchange code with code_verifier
    CO->>KC: save token set (service god-market-tech-analysis)
    CO-->>API: status (accepted or error)
    API-->>UI: status JSON "Authorization callback accepted."
```

Until the callback completes, chart-context requests return `503` rather than stale or fabricated data.

### 2.5 Watchlist snapshot sync (offline, read-only)

```mermaid
sequenceDiagram
    autonumber
    participant DEV as Developer
    participant SYNC as sync-mtf-watchlist.mjs
    participant DESK as TradingView Desktop (CDP 9222)
    participant FILE as data/mtf_watchlist.json

    DEV->>SYNC: --list "PS_Commodity" --default "PEPPERSTONE:NATGAS" [--dry-run]
    SYNC->>DESK: fetch /api/v1/symbols_list/custom/ (read only)
    DESK-->>SYNC: symbols and sections
    alt default not in list
        SYNC-->>DEV: error, nothing written
    else valid
        alt dry-run
            SYNC-->>DEV: print summary only
        else write
            SYNC->>FILE: write snapshot (watchlist_name, default_symbol, sections, recorded date)
        end
    end
```

---

## Part 3 - Low-level design (LLD)

### 3.1 Backend module map

```mermaid
flowchart LR
    APP["app.py<br/>create_app, routes"]

    subgraph UC["Use cases"]
        MTFA["mtf_analysis.py<br/>MultiTimeframeAnalysisService<br/>live candle, display_name"]
        GMS["global_market.py<br/>GlobalMarketLiveSnapshotProvider<br/>calculate_breadth"]
    end

    subgraph ORCH["Orchestration and cache"]
        ORC["mtf_orchestrator.py<br/>MultiTimeframeContextOrchestrator"]
        CACHE["mtf_cache.py<br/>LocalContextCache"]
        POL["mtf_policy.py<br/>FreshnessPolicy, classify_freshness"]
    end

    subgraph ENGINE["Analysis engine (pure)"]
        CHK["mtf_checklist.py<br/>CHECKLIST_ROWS, evaluate_timeframe"]
        SCR["mtf_screens.py<br/>LAYERS, double_screen, triple_screen"]
        IND["technical_indicators.py<br/>calculate_indicators"]
        PS["price_structure.py<br/>find_pivots, dow_trend, price_action"]
    end

    subgraph ADAPT["Adapters"]
        PROV["providers.py<br/>OfficialMCPProvider"]
        OAUTH["oauth.py<br/>OfficialMCPOAuthCoordinator"]
        DESK["desktop_bridge.py<br/>TradingViewDesktopWatchlistReader"]
    end

    MODELS["models.py<br/>all Pydantic models"]

    APP --> MTFA
    APP --> GMS
    APP --> OAUTH
    APP --> PROV
    MTFA --> ORC
    MTFA --> CHK
    MTFA --> SCR
    ORC --> CACHE
    ORC --> PROV
    CACHE --> POL
    CHK --> IND
    CHK --> PS
    SCR --> CHK
    GMS --> PROV
    GMS --> DESK
    DESK --> PROV
    PROV -. MCP session from .-> OAUTH
    MTFA -.-> MODELS
    ORC -.-> MODELS
    CHK -.-> MODELS
    SCR -.-> MODELS
    GMS -.-> MODELS
```

Module dependency rules that hold in the code:
- `technical_indicators.py`, `price_structure.py` and `mtf_checklist.py` do no I/O.
- Only `providers.py`, `oauth.py` and `desktop_bridge.py` talk to TradingView or the keychain.
- `app.py` is the only place where services are wired together.

### 3.2 Core data model

```mermaid
classDiagram
    class Candle {
        timestamp
        open
        high
        low
        close
        volume
    }
    class ChartContext {
        symbol
        timeframe
        source
        source_timestamp
        freshness_state
        candles
        technicals
        warnings
    }
    class MultiTimeframeContext {
        symbol
        requested_at
        completeness
        contexts
        layers
        warnings
    }
    class TimeframeEvaluation {
        cells
        series
        last_close
        last_candle_at
        unavailable_reason
    }
    class ChecklistRow {
        id
        section
        label
        automated
    }
    class ChecklistCell {
        labels
        bias
        values
        rule_ids
        unavailable_reason
    }
    class TimeframeScreen {
        signal
        labels
        unavailable_reason
    }
    class LayerSignal {
        name
        timeframes
        screen_indicator
        signal
        screens
        missing_timeframes
    }
    class ScreenDecision {
        name
        layers
        decision
        position_note
        missing_timeframes
    }
    class MultiTimeframeAnalysis {
        symbol
        display_name
        requested_at
        profile_version
        completeness
        timeframes
        layers
        rows
        decisions
        warnings
    }
    class MtfInstrumentCatalog {
        watchlist_name
        default_symbol
        sections
    }

    ChartContext --> Candle : has many
    MultiTimeframeContext --> ChartContext : per timeframe
    TimeframeEvaluation --> ChecklistCell : one per row id
    ChecklistRow --> ChecklistCell : evaluated into
    LayerSignal --> TimeframeScreen : per timeframe
    MultiTimeframeAnalysis --> LayerSignal : layers
    MultiTimeframeAnalysis --> ChecklistRow : rows
    MultiTimeframeAnalysis --> ScreenDecision : decisions
    MtfInstrumentCatalog --> MultiTimeframeAnalysis : symbol must be in
```

### 3.3 Per-timeframe evaluation (`evaluate_timeframe`)

```mermaid
flowchart TD
    C["Candles from ChartContext"] --> IND["calculate_indicators<br/>profile mtf-checklist-v1"]
    IND --> SER["Indicator series<br/>EMA 5/13/26/50/100/150/200, RSI 14, MACD,<br/>Bollinger 20, Stochastic 14/3, ATR 14, DMI/ADX 14"]
    C --> PIV["find_pivots left=5 right=5"]
    PIV --> DOW["dow_trend<br/>HH-HL = UP, LL-LH = DOWN, else SIDEWAYS"]
    C --> PA["locate_price, price_action,<br/>detect_candle_patterns"]
    SER --> CELLS["Checklist cells<br/>bollinger_cell, rsi_cell, dmi_cell, adx_cell,<br/>macd_cell, stochastic_cell, ema_cell"]
    CELLS -. "ChecklistCell: labels, bias, values, rule_ids" .-> ROWS
    CELLS --> ROWS["CHECKLIST_ROWS (21 rows)"]
    DOW --> EVAL
    PA --> EVAL
    ROWS --> EVAL["TimeframeEvaluation"]
    SER --> EVAL
    EVAL --> SCR["evaluate_screens (see 3.4)"]
```

Indicator conventions match TradingView Pine:
- EMA is seeded with an SMA.
- RSI, ATR and DMI/ADX use Wilder's RMA.
- Bollinger Bands use the population standard deviation.

Thresholds come from `ChecklistThresholds` (version `mtf-checklist-v1`): recent-crossover window 3, slope lookback 3, RSI neutral band 45 to 55, Bollinger near-median fraction 0.10, Bollinger flat tolerance 0.005, S/R proximity 1.0 ATR, MACD near-zero fraction 0.10, pivot window 5, Dow v2 significance 0.5 ATR, wick tolerance 0.02. The additive Dow v2 row uses only closed candles, normalizes alternating swings, and reports contracting/expanding ranges plus structure breaks; it does not feed screen decisions.

### 3.4 Screen decisions (`evaluate_screens`)

```mermaid
flowchart TD
    subgraph LAYERS["Layers (mtf_screens.LAYERS)"]
        SUP["Super TIDE<br/>Monthly + Weekly<br/>MACD"]
        TIDE["TIDE<br/>Daily + 4H<br/>MACD"]
        WAVE["WAVE<br/>4H + 1H<br/>Stochastic / RSI"]
        RIP["RIPPLE<br/>1H + 15m<br/>MACD"]
    end

    SUP --> LS1["layer_signal<br/>all timeframes agree = BUY or SELL<br/>any missing = UNAVAILABLE<br/>disagree = NOT CLEAR"]
    TIDE --> LS1
    WAVE --> LS1
    RIP --> LS1

    LS1 --> D1["Double Screen<br/>TIDE + WAVE (headline)"]
    LS1 --> D2["Double Screen<br/>Super TIDE + TIDE"]
    LS1 --> D3["Double Screen<br/>WAVE + RIPPLE"]
    LS1 --> T1["Triple Screen<br/>TIDE + WAVE + RIPPLE"]

    D1 --> OUT["MtfDecisions"]
    D2 --> OUT
    D3 --> OUT
    T1 --> OUT

    OUT --> RULE["Rule order per decision:<br/>1. any missing timeframe -> INCOMPLETE — tf unavailable<br/>2. any NOT CLEAR layer -> NOT CLEAR<br/>3. otherwise match layer directions"]
```

Decision text examples: `BUY`, `SELL`, `No Buy — wait for WAVE to align with TIDE`, and `INCOMPLETE — 4h unavailable`. The response carries one disclaimer at `decisions.disclaimer`: `Checklist signal derived from the SMM Double/Triple Screen rules — not financial advice.`

### 3.5 Cache and freshness

```mermaid
stateDiagram-v2
    [*] --> Miss
    Miss --> Fetched: provider returns candles
    Fetched --> Fresh: age <= fresh_for
    Fresh --> Stale: age > fresh_for
    Stale --> Expired: age > stale_for
    Stale --> Fresh: force_refresh succeeds
    Expired --> Fetched: next request fetches again
    Miss --> Unavailable: provider fails
    Unavailable --> Fetched: next request retries
```

Freshness is measured from the latest candle's source timestamp, not from when the cache entry was written.

| Timeframe | `fresh_for` | `stale_for` |
| --- | --- | --- |
| Monthly | 40 days | 70 days |
| Weekly | 9 days | 16 days |
| Daily | 36 hours | 72 hours |
| 4H | 6 hours | 14 hours |
| 1H | 2 hours | 5 hours |
| 15m | 35 minutes | 2 hours |

Default for any other timeframe: 36 hours and 72 hours. The cache is per process and keyed by source, symbol and timeframe. It stores no raw payloads and no credentials.

Stale handling: `MultiTimeframeAnalysisService` refetches stale timeframes once with `force_refresh`. If that fetch fails, the earlier stale context stays and the response reports it as `STALE`.

### 3.6 Orchestrator concurrency

```mermaid
flowchart LR
    REQ["get_context(symbol, timeframes)"] --> GATHER["asyncio.gather<br/>one task per timeframe"]
    GATHER --> R1["resolve(tf)"]
    R1 --> HIT{"cache hit<br/>and not force_refresh?"}
    HIT -- yes --> RET["return context"]
    HIT -- no --> INF{"in-flight task for<br/>(symbol, tf)?"}
    INF -- yes --> SHIELD["await shielded task"]
    INF -- no --> NEW["create task"]
    NEW --> SEM["Semaphore(3)<br/>provider call"]
    SEM --> PUT["cache.put on success"]
    PUT --> DONE["remove from in-flight map"]
    SHIELD --> RET
    DONE --> RET
    SEM -. DataSourceUnavailableError .-> UNAV["TimeframeContextResult<br/>unavailable_reason"]
```

Two requests for the same symbol and timeframe share one provider call. A cancelled caller does not cancel the shared task.

### 3.7 Live candle rule

```mermaid
flowchart TD
    S["symbol e.g. MCX:GOLD1!"] --> EX["exchange_of(symbol)<br/>prefix before colon"]
    EX --> Q{"SESSION_CLOSE_BY_EXCHANGE"}
    Q -- "NSE 15:30 IST" --> SESS["session close on the candle's day"]
    Q -- "MCX 23:30 IST" --> SESS
    Q -- "not listed (CFD, global)" --> CL2["candle_closes_at, around the clock<br/>Monthly: calendar month end<br/>Weekly, Daily, intraday: opened + period"]
    SESS --> CL["candle_closes_at, session based<br/>Monthly: last weekday of month at session close<br/>Weekly: Friday session close<br/>Daily: session close same day<br/>Intraday: min(opened + period, session close)"]
    CL --> CHK{"now < closes_at?"}
    CL2 --> CHK
    CHK -- yes --> BADGE["live badge: candle still forming"]
    CHK -- no --> CLOSED["closed candle"]
```

Known limit: MCX holiday calendars and DST schedules are not modelled. The MCX 23:30 close is a fixed approximation.

### 3.8 Frontend structure

```mermaid
flowchart TD
    MAIN["main.tsx"] --> PROV["AppProviders<br/>TanStack QueryClient, Ant Design theme"]
    PROV --> APPC["App.tsx<br/>header nav, theme toggle"]
    APPC --> R1["/global-market"]
    APPC --> R2["/multi-timeframe"]
    APPC --> R3["* redirects to /global-market"]

    R1 --> GMP["GlobalMarketPage.tsx"]
    GMP --> GMH["useGlobalMarket.ts"]
    GMP --> GMC["SentimentSummary, MarketGroupCards,<br/>MarketGroupTable, MarketGroupHeader"]
    GMP --> GMD["MarketInstrumentDetailDrawer.tsx"]

    R2 --> MTP["MultiTimeframePage.tsx"]
    MTP --> MTH["useMultiTimeframe.ts<br/>instruments and analysis queries"]
    MTP --> MTC["DecisionStrip.tsx<br/>Double and Triple Screen"]
    MTP --> MTM["ChecklistMatrix.tsx<br/>21 rows x 6 timeframes"]
    MTM --> MTD["MatrixDetailDrawer.tsx"]
    MTP --> MTF["mtfFormat.ts"]

    GMH --> CLIENT["api/client.ts<br/>apiBaseUrl = /api/v1"]
    MTH --> CLIENT
    CLIENT -- "Vite proxy /api" --> API["FastAPI :8000"]

    APPC --> STORE["state/uiStore.ts<br/>zustand persist 'god-market-ui'<br/>themeMode"]
```

The MTF page opens one WebSocket per selected symbol (`useMtfLive`) and writes each update into the analysis query cache. Reconnect uses exponential backoff and a 90-second silence watch. The analysis query is keyed by symbol. The instruments catalogue uses `staleTime: Infinity`. A refresh calls `getMtfAnalysis(symbol, 'force_refresh')` and writes the result into the query cache. The Global Market query is keyed by timeframe. The instrument dropdown is grouped by section (`INTERNATIONAL - STUDY, TA ANALYSIS` and `INDIA MCX`), and the default is `PEPPERSTONE:NATGAS`.

### 3.9 API contract

| Method and path | Purpose | Success | Errors |
| --- | --- | --- | --- |
| `GET /health` | Service and source readiness | `200 ServiceHealth` | none |
| `GET /api/v1/chart-context/{symbol}?timeframe=` | One normalised chart context | `200 ChartContext` | `503` when the provider raises `DataSourceUnavailableError` (for example, OAuth not connected) |
| `GET /api/v1/multi-timeframe-context/{symbol}?timeframe=` (repeatable) | Assembled timeframe evidence | `200` complete or partial | `503` with a typed result when no timeframe is usable |
| `GET /api/v1/mtf-analysis/instruments` | `PS_Commodity` catalogue | `200 MtfInstrumentCatalog` | none |
| `GET /api/v1/mtf-analysis/{symbol}?refresh_mode=prefer_cache\|force_refresh` | Checklist, layers, screens | `200 MultiTimeframeAnalysis` | `422` symbol outside snapshot |
| `GET /api/v1/global-market-sentiment?timeframe=` | Ordered `PS_Global_Indices` groups and breadth | `200 GlobalMarketSnapshot` | no HTTP error mapping; unavailable items are marked with warnings |
| `GET /api/v1/oauth/official/status` | OAuth state: status, completed time, tool count, error | `200` | none; errors appear in the `error` field |
| `POST /api/v1/oauth/official/start` | Begin PKCE authorization | `200` with `authorization_url` | `502` when the flow cannot start |
| `GET /api/v1/oauth/official/callback?code&state` | Complete the authorization | `200` status message | errors are reported through the coordinator status |

### 3.10 Error and degradation handling

| Condition | Where it is caught | User-visible result |
| --- | --- | --- |
| OAuth not connected | `OfficialMCPProvider` raises `DataSourceUnavailableError` | Timeframe `UNAVAILABLE` with reason; screen `INCOMPLETE` |
| MCP call fails for another reason | Orchestrator catch-all | Generic "could not provide this timeframe" reason |
| Symbol not in snapshot | `UnknownInstrumentError` in service | `422` |
| Keychain read or write fails | `OAuthStorageError` | OAuth status reports the error; no tokens are printed |
| OAuth start fails | Coordinator error | `502` from `POST /oauth/official/start` |
| Desktop bridge not configured | Desktop reader | Global warning: fallback unavailable |
| Global official request stalls | Time budget 20 s, failure limit 3 | Remaining items go to Desktop fallback or stay unavailable; warning names the stop reason |
| Stale candles | `FreshnessPolicy` | One refresh; stale kept if refresh fails |
| Watchlist snapshot missing or invalid | Service constructor | Backend fails to start (fail fast) |
| Rate limit on the chart-context technical snapshot | Provider | OHLCV still returned; warning shown (the MTF checklist uses OHLCV only) |

### 3.11 Storage and state

| Store | Contents | Lifetime | Secrets |
| --- | --- | --- | --- |
| `data/mtf_watchlist.json` | `watchlist_name`, `default_symbol`, sections with symbols, recorded date | Committed file, changed only by the sync script | No |
| In-memory `LocalContextCache` | Normalised `ChartContext` per source, symbol and timeframe | Process lifetime | Raw payloads and credentials are not stored |
| In-memory Global Market snapshot cache | Last snapshot per timeframe, 60 s | Process lifetime | No |
| macOS Keychain, service `god-market-tech-analysis` | OAuth token set and client info | Until revoked | Yes, OS-protected |
| Browser `localStorage`, key `god-market-ui` | `themeMode` | Browser profile | No |
| `.env.local` | Path to the Desktop bridge CLI | Machine-specific, git-ignored | No |

### 3.12 Configuration constants

| Constant | Value | Where |
| --- | --- | --- |
| `SNAPSHOT_PATH` | `src/god_market_api/data/mtf_watchlist.json` | `mtf_analysis.py` |
| `SESSION_CLOSE_BY_EXCHANGE` | NSE 15:30, MCX 23:30 (IST) | `mtf_analysis.py` |
| Orchestrator concurrency | 3 | `mtf_orchestrator.py` |
| Global Market concurrency | 6, 1 retry, 20 s budget, failure limit 3 | `global_market.py` |
| Official candle count | 500 for MTF, 2 for Global Market | `providers.py` |
| OAuth redirect | `http://127.0.0.1:8000/api/v1/oauth/official/callback` | `oauth.py` |
| Keychain service | `god-market-tech-analysis` | `oauth.py` |
| CDP port | 9222 | `start-local.sh`, `sync-mtf-watchlist.mjs` |
| Vite dev port and proxy | 5173, `/api` to `127.0.0.1:8000` | `frontend/vite.config.ts` |

---

## Part 4 - Verification

- Backend: 187 pytest tests passing (`uv run pytest`). Covers the instruments endpoint, analysis endpoint, 422 path, stale refresh, and the live-candle rule for NSE, MCX and around-the-clock CFDs.
- Frontend: 18 Vitest tests passing. Lint, typecheck and build clean.
- Live check: `PEPPERSTONE:NATGAS` returned `complete` with all six timeframes live.

Source files for this document: `src/god_market_api/*.py`, `scripts/start-local.sh`, `scripts/sync-mtf-watchlist.mjs`, `frontend/src/**`.
