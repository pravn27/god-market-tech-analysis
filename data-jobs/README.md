# Data jobs

Scheduled jobs that store daily market bars for the Global Market instruments in SQLite, record how each run went, and show the progress on a local page.

This folder is a separate Python package. It reuses the live app's `god_market_api` package for the TradingView Desktop bridge, the chart reader, the chart lock and the MCP provider.

| Read this | For |
| --- | --- |
| This README | Commands, layout, configuration, tests |
| [Operations runbook](../docs/operations/data-jobs-runbook.md) | Install, schedule, daily use, monitoring, recovery |
| [System design](../docs/architecture/data-jobs-system-design.md) | Components, data model, run lifecycle, failure behaviour, decisions, known limits |

## What it does

- **Job `global-market-daily`** (once a day): reads the instrument list from the TradingView Desktop watchlist `PS_Global_Indices`. Then it fetches 300 daily bars per instrument, from the official MCP first and from the open Desktop chart only if the MCP quota is used up.
- **Derived bars:** weekly, monthly and quarterly bars are built from the stored daily bars. Nothing extra is fetched for them.
- **Trading days:** each daily bar is stored under its trading day, using the instrument's exchange time zone. This keeps futures weekly and monthly boundaries right.
- **Retries:** a failed item is retried once in the same run. A partial run is retried an hour later for its failed symbols only, up to four runs per day.
- **Telemetry:** every run, item, error and period is recorded, and shown by `status` and the page.
- **Schedule:** a macOS launchd agent wakes `tick` every hour. The database decides which job is due.

## Requirements

- macOS, with the repo's `.venv` (Python 3.14 is used; the package declares `>=3.10`).
- TradingView Desktop open, with `PS_Global_Indices` as the visible watchlist. Without it, no job runs.
- For daily bars from the MCP: an authenticated official MCP (see the [OAuth runbook](../docs/operations/official-mcp-oauth-runbook.md)).
- For the Desktop fallback and the instrument list: `TRADINGVIEW_DESKTOP_BRIDGE_CLI` and `TRADINGVIEW_DESKTOP_BRIDGE_NODE` in the app's `.env.local`.

The package's own code uses only the standard library, but it imports the live app's `god_market_api`, so run it with the repo `.venv`, which has the app's dependencies. Tests need `pytest`, also in that `.venv`.

## Commands

Set this once in your shell, or use the full path each time:

```
cd /Users/pshekarappa/pravn27/ASTA/god-market-tech-analysis/data-jobs
DJ="env PYTHONPATH=src:../src /Users/pshekarappa/pravn27/ASTA/god-market-tech-analysis/.venv/bin/python -m data_jobs"
```

| Command | What it does |
| --- | --- |
| `$DJ status` | Each job's schedule, next run, last full success, latest run progress, and recent coverage. Works without Desktop; coverage is hidden if the instrument list cannot be read. |
| `$DJ tick` | Runs every job that is due. Exit codes: `0` ok, `2` no bar source, `3` instrument list unavailable (Desktop closed or wrong watchlist). |
| `$DJ ui` | Serves the progress page at <http://127.0.0.1:8765>. Read-only. Options: `--port 8766`, `--host 127.0.0.1`. Stop with Ctrl+C. |
| `$DJ schedule install` | Writes and loads the launchd agent (hourly tick, runs now). Copies the bridge settings from `.env.local`. Options: `--every-minutes 60`. |
| `$DJ schedule status` | Shows whether the agent is installed and loaded. |
| `$DJ schedule uninstall` | Unloads the agent and deletes its file. Stored data is kept. |

Global option: `--db PATH` (default `data-jobs/data/jobs.sqlite3`, or set `DATA_JOBS_DB`).

Example output of `status`:

```
global-market-daily: every 1d; next run 2026-10-23T15:43:12Z; last success never; latest run partial: 34/34 done, 19 failed
  coverage, newest first: 2026-10-22 partial, 2026-10-21 missing, ...
```

`last success never` means no run has **fully** succeeded yet, even when most symbols are stored. The page shows the same figure as "Last fully successful run".

## Quick start

1. Open TradingView Desktop and make `PS_Global_Indices` the visible watchlist.
2. Check the instrument list (read-only, no quota):

   ```
   $DJ status
   ```

3. Start the page in one terminal and leave it open:

   ```
   $DJ ui
   ```

4. Open <http://127.0.0.1:8765>.
5. When you are ready for the first daily run (about 20 to 30 minutes, uses Desktop chart time and MCP quota), install the schedule:

   ```
   $DJ schedule install
   ```

   Or run it once by hand with `$DJ tick`.

## Layout

```
data-jobs/
  README.md
  pyproject.toml
  data/                       jobs.sqlite3 (default database), backups        not in git
  src/data_jobs/
    cli.py                    commands
    registry.py               job specs; instrument list from the Desktop watchlist
    runner.py                 run lifecycle, retries, due checks, stalled runs
    fallback.py               MCP first; Desktop only on quota, daily only, budget
    mcp.py                    daily candles from the official MCP
    desktop.py                daily candles from the open Desktop chart
    trading_day.py            trading-day rule, exchange zones, evening-open list
    aggregate.py              weekly, monthly, quarterly bars from daily bars
    candles.py                candle to bar conversion
    store.py                  SQLite schema and transactions
    telemetry.py              the page's JSON
    web.py                    the page and /api/status
    scheduler.py              launchd agent
    rekey.py                  one-time re-dating of stored bars (already applied; do not rerun)
    config.py                 absolute paths
  tests/                      pytest suite
```

## Configuration

| Setting | Where | Default | Meaning |
| --- | --- | --- | --- |
| `DATA_JOBS_DB` | environment or `--db` | `data/jobs.sqlite3` | Database file |
| `TRADINGVIEW_DESKTOP_BRIDGE_CLI` | environment, or `.env.local` at install | none | Path to the bridge CLI (`src/cli/index.js`) |
| `TRADINGVIEW_DESKTOP_BRIDGE_NODE` | environment, or `.env.local` at install | `node` | Node binary for the bridge |

Constants that set behaviour are in code, and are described in the system design:

| Constant | File | Value |
| --- | --- | --- |
| `DAILY_BAR_COUNT` | `registry.py` | 300 bars per instrument per run |
| `DEFAULT_DESKTOP_READ_BUDGET` | `fallback.py` | 80 Desktop reads per run |
| `FAILED_RETRY_AFTER` | `runner.py` | 1 hour |
| `MAX_RUNS_PER_PERIOD` | `runner.py` | 4 runs per UTC day, including the first |
| `STALE_AFTER` | `runner.py` | 10 minutes without a heartbeat means stalled |
| `OVERDUE_GRACE` | `runner.py` | 2 hours past due |
| `SESSION_ZONES`, `EVENING_OPEN` | `trading_day.py` | 34 instruments, 5 evening-open |

## Tests

```
cd /Users/pshekarappa/pravn27/ASTA/god-market-tech-analysis/data-jobs
../.venv/bin/python -m pytest
```

All 99 tests should pass. They use an in-memory SQLite database and fake sources, so they need no TradingView, no MCP and no network. The page tests use `127.0.0.1` only.

| Test file | Covers |
| --- | --- |
| `test_store.py` | Schema, transactions, upserts and change counts |
| `test_runner.py` | Run status, next run, coverage, stalled runs, overdue |
| `test_retry.py` | In-run retry, targeted retry an hour later, the cap, new-day behaviour |
| `test_fallback.py` | Quota-only fallback, daily-only, budget, Desktop open check |
| `test_mcp.py`, `test_desktop.py` | The two daily sources and their error mapping |
| `test_aggregate.py` | Weekly, monthly, quarterly boundaries and partial volume |
| `test_derived.py` | Derived bars from stored daily bars, held-back partial periods |
| `test_trading_day.py` | Trading-day rule, evening-open list, re-keying |
| `test_registry.py` | Instrument list from the watchlist, refusal of the wrong watchlist |
| `test_cli.py` | Commands, exit codes, bridge settings from `.env.local` |
| `test_scheduler.py` | launchd plist and install, uninstall, status |
| `test_telemetry.py`, `test_web.py` | Page JSON, server routes, missing database |

## Troubleshooting

| You see | Look at |
| --- | --- |
| `Instrument list unavailable` | Desktop is open with `PS_Global_Indices` visible |
| Items failing with `did not load ... in time` | Desktop chart load; see the runbook |
| Nothing happens on schedule | `$DJ schedule status`, then `~/Library/Logs/data-jobs/tick.log` |
| Page says "No database yet" | No run has happened; run `$DJ tick` or wait for the schedule |

More detail: [operations runbook](../docs/operations/data-jobs-runbook.md).

## Status and limits

- The official MCP path is implemented and tested with fakes, but **not yet run live**.
- Weekly and monthly bars are not yet compared to TradingView's own charts.
- macOS only. Windows scheduling is not built.
- Intraday (4H, 1H) jobs are not built.

Full list: [system design, section 13](../docs/architecture/data-jobs-system-design.md#13-known-limitations-and-open-risks).
