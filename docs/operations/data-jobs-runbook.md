# Data jobs runbook

How to install, schedule, use, watch and recover the Global Market data jobs on this Mac. For what the system is and why, read the [data-jobs system design](../architecture/data-jobs-system-design.md). For the commands, read the [data-jobs README](../../data-jobs/README.md).

All commands below run from the `data-jobs` folder unless stated otherwise:

```
cd /Users/pshekarappa/pravn27/ASTA/god-market-tech-analysis/data-jobs
```

The shorthand `DJ` below means:

```
PYTHONPATH=src:../src /Users/pshekarappa/pravn27/ASTA/god-market-tech-analysis/.venv/bin/python -m data_jobs
```

Use the full command, or define `DJ` in your shell.

## 1. One-time setup

1. **Install dependencies.** The repo `.venv` is used. Nothing else to install.
2. **Check the bridge settings** in the app's ignored `.env.local`. These must be present before the agent is installed, because the agent copies them:

   ```
   TRADINGVIEW_DESKTOP_BRIDGE_CLI=/path/to/tradingview-bridge/src/cli/index.js
   TRADINGVIEW_DESKTOP_BRIDGE_NODE=/path/to/node
   ```

3. **Authenticate the official MCP** if it has not been done. See the [official MCP OAuth runbook](official-mcp-oauth-runbook.md).
4. **Open TradingView Desktop** and make `PS_Global_Indices` the visible watchlist. Confirm with:

   ```
   DJ status
   ```

   It should not print `Instrument list unavailable` on its own. If it does, the message says why (usually Desktop is closed, or another watchlist is visible).
5. **Run the tests** once to confirm the install:

   ```
   ../.venv/bin/python -m pytest
   ```

   The expected result is all tests passing (99 at the time of writing).

## 2. Turn on the schedule

```
DJ schedule install
```

This writes `~/Library/LaunchAgents/com.asta.data-jobs.tick.plist`, copies the two bridge settings from `.env.local` into it, and loads it. The agent runs `tick` once now and then every 60 minutes.

**Note:** `install` runs a tick immediately. If Desktop is open and the watchlist is visible, that tick starts the daily job, which uses MCP quota and Desktop chart time for roughly 20 to 30 minutes. Run it when you are ready for that.

Check it:

```
DJ schedule status
```

Expected: `com.asta.data-jobs.tick: loaded; agent file present.`

To stop the schedule:

```
DJ schedule uninstall
```

This unloads the agent and deletes the plist. Stored data is not touched.

## 3. Daily use

| You want to | Do this |
| --- | --- |
| See each job's schedule and latest run | `DJ status` |
| Open the progress page | `DJ ui`, then open <http://127.0.0.1:8765> |
| Run due jobs now, by hand | `DJ tick` (requires Desktop open for the instrument list) |
| Read the scheduled runs' output | `tail -n 50 ~/Library/Logs/data-jobs/tick.log` |
| Read the scheduled runs' errors | `tail -n 50 ~/Library/Logs/data-jobs/tick.err.log` |

You do not need to do anything for the scheduled runs to happen, provided the Mac is on, awake at the time, and TradingView Desktop is open with `PS_Global_Indices` visible. Without Desktop, the tick exits with code 3 and nothing runs; that is expected, and the next tick tries again.

### 3.1 Reading `status`

```
global-market-daily: every 1d; next run 2026-10-23T15:43:12Z; last success never; latest run partial: 34/34 done, 19 failed
  coverage, newest first: 2026-10-22 partial, 2026-10-21 missing, ...
```

| Field | Meaning |
| --- | --- |
| `every 1d` | The job's interval |
| `next run` | When the job is next due. `now` means due at the next tick |
| `last success` | The most recent run that **fully** succeeded. `never` means no run has fully succeeded yet, even if most symbols are stored |
| `latest run` | Status of the newest run, and `done` / `failed` out of the total items |
| `coverage` | One entry per recent day: `succeeded`, `partial`, `failed`, `running`, `missing` (no run that day) or `pending` (today, not yet run) |
| `OVERDUE` | The job was due more than 2 hours ago and has not started |

### 3.2 Reading the page

- **Progress bar:** done out of total. A red bar means at least one failure.
- **Failed items:** expand to see each symbol and its error text.
- **All items:** every symbol of the latest run, with its fetch time.
- **Recent runs:** newest first. The last column shows bars new / changed / unchanged.

The page refreshes every 3 seconds while it is open. Close the terminal running `DJ ui` to stop it.

## 4. What the statuses mean for you

| Run status | What to do |
| --- | --- |
| `succeeded` | Nothing. |
| `partial` | Nothing, usually. The failed symbols are retried in an hour, then again up to four runs in total for the day. Check the errors if the same symbols keep failing. |
| `failed` | Check the errors. The usual cause is Desktop: charts not loading, or Desktop closed. Retries run automatically. |
| `stalled` | The previous run was killed or the Mac slept mid-run. The next run recovers. Nothing to do. |
| `running` | Wait. Watch the progress bar, or run `DJ status` again. |

| Error text | Cause | What to do |
| --- | --- | --- |
| `DataSourceUnavailableError: TradingView Desktop did not load <SYMBOL> at 1D in time.` | The chart took longer than 30 seconds to load | Usually none. Leave Desktop open and idle. Repeated failures for the same symbols: restart TradingView Desktop. |
| `UnknownSessionZone: No exchange time zone is set for <SYMBOL>` | A new instrument was added to the watchlist | Add the instrument to `SESSION_ZONES` in `data-jobs/src/data_jobs/trading_day.py`, and to `EVENING_OPEN` if its session opens in the evening. Then run the tests. |
| `EmptyResponseError: The source returned no bars.` | The source answered with nothing | Check that the symbol has data in TradingView. |
| `QuotaExhaustedError: ...` | The MCP quota is used up and the Desktop fallback did not apply | Wait for the quota to reset at 00:00 UTC, or check that Desktop is open. |
| `ValueError: Two daily bars for ... fall on the same trading day` | Two source bars map to one trading day | Report it. Do not edit the data. |

## 5. Recovery

### 5.1 A run is stuck as `running`

A run is stuck only if its process is alive but not moving. Check:

```
ps -axo pid,etime,command | grep data_jobs | grep -v grep
```

- If a `data_jobs tick` process is running and its elapsed time is well over 30 minutes, it is probably waiting on Desktop. Quit TradingView Desktop and watch the progress page: the remaining items should fail and the run should finish. If the process is still running after several minutes, stop it with `kill <pid>`. The next run will mark the run `stalled` and continue.
- If no process is running, the next tick marks the run `stalled` after its heartbeat is 10 minutes old, and starts a new run.

Do not delete rows from `job_runs` by hand.

### 5.2 The scheduled run is failing every hour

Look at the error log:

```
tail -n 20 ~/Library/Logs/data-jobs/tick.err.log
tail -n 20 ~/Library/Logs/data-jobs/tick.log
```

- `Instrument list unavailable` in `tick.log`: Desktop is closed or `PS_Global_Indices` is not the visible watchlist. Open it.
- A Python traceback in `tick.err.log`: a code or dependency problem. Run `DJ tick` by hand to see it.

### 5.3 The agent was loaded with the wrong settings

Reinstall:

```
DJ schedule uninstall
DJ schedule install
```

Remember that `install` runs a tick immediately (see section 2).

### 5.4 Restore the database from a backup

Stop the page first (`Ctrl+C` in its terminal). Then, with the schedule paused (`DJ schedule uninstall`):

```
cp data/jobs.sqlite3 data/jobs.sqlite3.before-restore
cp data/jobs.sqlite3.before-<tag>.bak data/jobs.sqlite3
rm -f data/jobs.sqlite3-wal data/jobs.sqlite3-shm
```

Then run `DJ schedule install` again.

### 5.5 Start the page on another port

```
DJ ui --port 8766
```

Use the same database. The default port is 8765.

## 6. One-time operations already applied

### 6.1 Trading-day re-keying (applied on 22 Oct 2026)

The daily bars stored before the trading-day rule used the raw Desktop stamp as their key. They were re-keyed once with `rekey_daily_bars` in `data-jobs/src/data_jobs/rekey.py`, and the weekly, monthly and quarterly bars were rebuilt. A backup was taken first:

```
data-jobs/data/jobs.sqlite3.before-trading-day-20261022-211436.bak
```

**Do not run `rekey_daily_bars` again.** It is not idempotent. Its input is the stored bar times. A bar already at trading-day midnight is read as a raw session stamp: for a morning-session New York instrument such as `TVC:SPX`, that moves it back one day. New runs do not need it: each fetch is re-dated from the raw source time on the way in.

If you ever need the same operation again, take a backup first, and write a new function for the new situation rather than rerunning this one.

## 7. Maintenance

| Task | When | How |
| --- | --- | --- |
| Back up the database | Before any change to data or code that writes bars | `cp data/jobs.sqlite3 data/jobs.sqlite3.before-<tag>.bak` with the schedule paused. Use SQLite's backup for a live copy if the schedule is running. |
| Clear old backups | When disk space matters | Delete the `.bak` files you no longer need. They are not read by anything. |
| Check what the database holds | Any time | `sqlite3 data/jobs.sqlite3 "select timeframe, source, count(*) from bars group by 1,2"` |
| Update the test suite | After changing any module | `../.venv/bin/python -m pytest` |

## 8. Known gaps

- The MCP call path has not been run live. Until it has, the scheduled runs use the Desktop chart for every daily bar.
- The MCP's timestamp convention is unverified (see the design doc, section 13).
- The Desktop chart timeout (30 seconds) is shared with the live app. Changing it affects both.
- The `data-jobs/data/` folder is not fully ignored by git. Only `*.sqlite3` is ignored, so backups and the `-wal` and `-shm` files show up as untracked.
- macOS only. Windows scheduling is not built.
