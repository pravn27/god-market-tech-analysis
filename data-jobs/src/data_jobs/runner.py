"""Runs jobs, records progress for every symbol and timeframe, and decides which jobs are due."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, List, Protocol, Sequence, Tuple, Union

from .store import Bar, from_text, to_text, transaction, upsert_bars, utc_now

Clock = Callable[[], datetime]

RUNNING = "running"
SUCCEEDED = "succeeded"
PARTIAL = "partial"
FAILED = "failed"
STALLED = "stalled"
SKIPPED = "skipped"
PENDING = "pending"
MISSING = "missing"

# A run whose heartbeat is older than this is assumed dead (crash, sleep, killed process).
STALE_AFTER = timedelta(minutes=10)
# After a run in which every item failed, retry sooner than the normal interval.
FAILED_RETRY_AFTER = timedelta(hours=1)
# A job still not started this long after it was due is reported as overdue.
OVERDUE_GRACE = timedelta(hours=2)
ERROR_LIMIT = 500


def daily_key(moment: datetime) -> str:
    """Period for a daily job: the UTC calendar date, for example 2026-10-22."""
    return moment.astimezone(timezone.utc).date().isoformat()


def weekly_key(moment: datetime) -> str:
    """Period for a weekly job: the ISO week, for example 2026-W43."""
    year, week, _ = moment.astimezone(timezone.utc).isocalendar()
    return f"{year}-W{week:02d}"


@dataclass(frozen=True)
class FetchResult:
    """Bars for one symbol and timeframe, with the source they were read from (stored on each row)."""

    bars: List[Bar]
    source: str


class BarFetcher(Protocol):
    """Reads recent bars for one symbol and timeframe."""

    def fetch(self, symbol: str, timeframe: str, *, count: int) -> FetchResult:
        ...


class EmptyResponseError(Exception):
    """The source answered but returned no bars, which is treated as a failed item."""


@dataclass(frozen=True)
class JobSpec:
    name: str
    interval: timedelta
    symbols: Tuple[str, ...]
    timeframes: Tuple[str, ...]
    bar_count: int
    # Which period a run belongs to, used to show coverage. Daily by default.
    period_key: Callable[[datetime], str] = daily_key

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("A job needs a name.")
        if self.interval.total_seconds() <= 0 or self.interval.total_seconds() != int(self.interval.total_seconds()):
            raise ValueError("A job interval must be a positive whole number of seconds.")
        if not self.symbols or not self.timeframes:
            raise ValueError("A job needs at least one symbol and one timeframe.")
        if self.bar_count <= 0:
            raise ValueError("A job must read at least one bar.")


@dataclass(frozen=True)
class RunResult:
    job_name: str
    run_id: Union[int, None]
    status: str
    items_failed: int = 0


@dataclass(frozen=True)
class ProgressCounts:
    total: int
    done: int
    failed: int


@dataclass(frozen=True)
class JobStatus:
    name: str
    interval_seconds: int
    next_run_at: Union[str, None]
    last_success_at: Union[str, None]
    latest_run_id: Union[int, None]
    latest_status: Union[str, None]
    progress: Union[ProgressCounts, None]
    overdue: bool


@dataclass(frozen=True)
class PeriodCoverage:
    period: str
    status: str


@dataclass
class _Totals:
    succeeded: int = 0
    failed: int = 0


def run_job(
    conn: sqlite3.Connection,
    spec: JobSpec,
    fetcher: BarFetcher,
    *,
    clock: Clock = utc_now,
) -> RunResult:
    """Run one job now. Returns ``skipped`` without fetching when another run of it is still active."""
    started = clock()
    with transaction(conn):
        _recover_stalled_runs(conn, started)
        if _has_active_run(conn, spec.name):
            return RunResult(job_name=spec.name, run_id=None, status=SKIPPED)
        _ensure_definition(conn, spec)
        cursor = conn.execute(
            "INSERT INTO job_runs (job_name, period_key, status, started_at, heartbeat_at, items_total) "
            "VALUES (?, ?, 'running', ?, ?, ?)",
            (
                spec.name,
                spec.period_key(started),
                to_text(started),
                to_text(started),
                len(spec.symbols) * len(spec.timeframes),
            ),
        )
        run_id = int(cursor.lastrowid)
        conn.executemany(
            "INSERT INTO job_items (run_id, symbol, timeframe, status) VALUES (?, ?, ?, 'queued')",
            [(run_id, symbol, timeframe) for symbol in spec.symbols for timeframe in spec.timeframes],
        )

    totals = _Totals()
    for symbol in spec.symbols:
        for timeframe in spec.timeframes:
            _run_item(conn, run_id, spec, fetcher, symbol, timeframe, clock, totals)
    return _finish_run(conn, spec, run_id, totals, clock())


def tick(
    conn: sqlite3.Connection,
    specs: Sequence[JobSpec],
    fetcher: BarFetcher,
    *,
    clock: Clock = utc_now,
) -> List[RunResult]:
    """Run every job whose next run time has passed. Jobs not yet due are left alone."""
    results: List[RunResult] = []
    for spec in specs:
        if _is_due(conn, spec.name, clock()):
            results.append(run_job(conn, spec, fetcher, clock=clock))
    return results


def job_status(conn: sqlite3.Connection, *, now: datetime) -> List[JobStatus]:
    statuses: List[JobStatus] = []
    rows = conn.execute(
        "SELECT name, interval_seconds, next_run_at, last_success_at FROM job_definitions ORDER BY name"
    ).fetchall()
    for row in rows:
        latest = conn.execute(
            "SELECT id, status FROM job_runs WHERE job_name = ? ORDER BY id DESC LIMIT 1",
            (row["name"],),
        ).fetchone()
        latest_status = latest["status"] if latest else None
        next_run_at = row["next_run_at"]
        # Overdue: the run was due more than the grace period ago, and nothing has started it since.
        overdue = (
            next_run_at is not None
            and from_text(next_run_at) + OVERDUE_GRACE < now
            and latest_status != RUNNING
        )
        statuses.append(
            JobStatus(
                name=row["name"],
                interval_seconds=int(row["interval_seconds"]),
                next_run_at=next_run_at,
                last_success_at=row["last_success_at"],
                latest_run_id=int(latest["id"]) if latest else None,
                latest_status=latest_status,
                progress=_progress(conn, int(latest["id"])) if latest else None,
                overdue=overdue,
            )
        )
    return statuses


def coverage(
    conn: sqlite3.Connection,
    spec: JobSpec,
    *,
    now: datetime,
    periods: int = 7,
) -> List[PeriodCoverage]:
    """Newest first: whether each recent period has a successful run, and whether any run happened."""
    keys: List[str] = []
    for step in range(periods):
        key = spec.period_key(now - step * spec.interval)
        if key not in keys:
            keys.append(key)
    current = spec.period_key(now)
    result: List[PeriodCoverage] = []
    for key in keys:
        statuses = [
            row["status"]
            for row in conn.execute(
                "SELECT status FROM job_runs WHERE job_name = ? AND period_key = ? ORDER BY id",
                (spec.name, key),
            )
        ]
        if SUCCEEDED in statuses:
            state = SUCCEEDED
        elif statuses:
            state = statuses[-1]
        elif key == current:
            state = PENDING
        else:
            state = MISSING
        result.append(PeriodCoverage(period=key, status=state))
    return result


def _run_item(
    conn: sqlite3.Connection,
    run_id: int,
    spec: JobSpec,
    fetcher: BarFetcher,
    symbol: str,
    timeframe: str,
    clock: Clock,
    totals: _Totals,
) -> None:
    try:
        result = fetcher.fetch(symbol, timeframe, count=spec.bar_count)
        if not result.bars:
            raise EmptyResponseError("The source returned no bars.")
        now = clock()
        with transaction(conn):
            counts = upsert_bars(
                conn,
                symbol=symbol,
                timeframe=timeframe,
                bars=result.bars,
                source=result.source,
                fetched_at=now,
            )
            conn.execute(
                "UPDATE job_items SET status = 'succeeded', fetched_at = ?, error = NULL "
                "WHERE run_id = ? AND symbol = ? AND timeframe = ?",
                (to_text(now), run_id, symbol, timeframe),
            )
            conn.execute(
                "UPDATE job_runs SET heartbeat_at = ?, bars_inserted = bars_inserted + ?, "
                "bars_updated = bars_updated + ?, bars_unchanged = bars_unchanged + ? WHERE id = ?",
                (to_text(now), counts.inserted, counts.updated, counts.unchanged, run_id),
            )
        totals.succeeded += 1
    except Exception as error:
        now = clock()
        with transaction(conn):
            conn.execute(
                "UPDATE job_items SET status = 'failed', fetched_at = ?, error = ? "
                "WHERE run_id = ? AND symbol = ? AND timeframe = ?",
                (to_text(now), _describe(error), run_id, symbol, timeframe),
            )
            conn.execute("UPDATE job_runs SET heartbeat_at = ? WHERE id = ?", (to_text(now), run_id))
        totals.failed += 1


def _finish_run(
    conn: sqlite3.Connection,
    spec: JobSpec,
    run_id: int,
    totals: _Totals,
    finished: datetime,
) -> RunResult:
    if totals.failed == 0:
        status = SUCCEEDED
    elif totals.succeeded == 0:
        status = FAILED
    else:
        status = PARTIAL
    next_run = finished + (FAILED_RETRY_AFTER if status == FAILED else spec.interval)
    with transaction(conn):
        conn.execute(
            "UPDATE job_runs SET status = ?, finished_at = ?, heartbeat_at = ? WHERE id = ?",
            (status, to_text(finished), to_text(finished), run_id),
        )
        conn.execute(
            "UPDATE job_definitions SET next_run_at = ?, "
            "last_success_at = CASE WHEN ? = 'succeeded' THEN ? ELSE last_success_at END WHERE name = ?",
            (to_text(next_run), status, to_text(finished), spec.name),
        )
    return RunResult(job_name=spec.name, run_id=run_id, status=status, items_failed=totals.failed)


def _recover_stalled_runs(conn: sqlite3.Connection, now: datetime) -> None:
    conn.execute(
        "UPDATE job_runs SET status = 'stalled', finished_at = ? WHERE status = 'running' AND heartbeat_at < ?",
        (to_text(now), to_text(now - STALE_AFTER)),
    )


def _has_active_run(conn: sqlite3.Connection, job_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM job_runs WHERE job_name = ? AND status = 'running' LIMIT 1",
        (job_name,),
    ).fetchone()
    return row is not None


def _ensure_definition(conn: sqlite3.Connection, spec: JobSpec) -> None:
    conn.execute(
        "INSERT INTO job_definitions (name, interval_seconds) VALUES (?, ?) "
        "ON CONFLICT (name) DO UPDATE SET interval_seconds = excluded.interval_seconds",
        (spec.name, int(spec.interval.total_seconds())),
    )


def _is_due(conn: sqlite3.Connection, job_name: str, now: datetime) -> bool:
    row = conn.execute("SELECT next_run_at FROM job_definitions WHERE name = ?", (job_name,)).fetchone()
    if row is None or row["next_run_at"] is None:
        return True
    return from_text(row["next_run_at"]) <= now


def _progress(conn: sqlite3.Connection, run_id: int) -> ProgressCounts:
    row = conn.execute(
        "SELECT COUNT(*) AS total, "
        "COALESCE(SUM(CASE WHEN status = 'queued' THEN 1 ELSE 0 END), 0) AS queued, "
        "COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0) AS failed "
        "FROM job_items WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    total = int(row["total"])
    return ProgressCounts(total=total, done=total - int(row["queued"]), failed=int(row["failed"]))


def _describe(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"[:ERROR_LIMIT]
