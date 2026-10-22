"""Command line: run due jobs, show schedules, progress and coverage, and manage the launchd schedule."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Sequence

from . import scheduler
from .config import DEFAULT_DB, GOD_MARKET_SRC_DIR, LOG_DIR, SRC_DIR
from .registry import bar_source, registered_jobs
from .runner import BarFetcher, JobSpec, JobStatus, coverage, job_status, tick
from .store import connect, utc_now

EXIT_NO_FETCHER = 2
EXIT_SCHEDULE_ERROR = 1
COVERAGE_PERIODS = 7


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    specs: Optional[Sequence[JobSpec]] = None,
    fetcher: Optional[BarFetcher] = None,
    clock: Callable[[], datetime] = utc_now,
    out: Callable[[str], None] = print,
) -> int:
    parser = argparse.ArgumentParser(prog="data-jobs", description="Run scheduled market-data jobs.")
    parser.add_argument(
        "--db",
        default=os.environ.get("DATA_JOBS_DB", str(DEFAULT_DB)),
        help="SQLite file holding bars and job telemetry (default: data-jobs/data/jobs.sqlite3, or $DATA_JOBS_DB).",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("tick", help="Run every job that is due.")
    commands.add_parser("status", help="Show each job's schedule, latest run and recent coverage.")
    schedule = commands.add_parser("schedule", help="Manage the macOS launchd agent that runs tick hourly.")
    actions = schedule.add_subparsers(dest="action", required=True)
    install = actions.add_parser("install", help="Install and load the agent, which runs now and then on the interval.")
    install.add_argument("--every-minutes", type=int, default=60, help="Interval between runs (default: 60).")
    actions.add_parser("uninstall", help="Unload the agent and delete its file.")
    actions.add_parser("status", help="Show whether the agent is installed and loaded.")
    args = parser.parse_args(argv)

    if args.command == "schedule":
        return _schedule(args, out)

    if specs is None:
        specs = registered_jobs()
    if fetcher is None:
        fetcher = bar_source()
    conn = connect(args.db)
    try:
        if args.command == "status":
            return _print_status(conn, specs, clock(), out)
        return _tick(conn, specs, fetcher, clock, out)
    finally:
        conn.close()


def run() -> None:
    raise SystemExit(main())


def _schedule(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    try:
        if args.action == "install":
            agent = scheduler.install(
                python=sys.executable,
                src_dirs=(SRC_DIR, GOD_MARKET_SRC_DIR),
                db=Path(args.db).resolve(),
                log_dir=LOG_DIR,
                every_seconds=args.every_minutes * 60,
            )
            out(f"Installed {scheduler.LABEL} at {agent}.")
            out(f"It runs every {args.every_minutes} minute(s) and once now. Logs: {LOG_DIR}")
        elif args.action == "uninstall":
            existed = scheduler.uninstall()
            out(f"Removed {scheduler.LABEL}." if existed else f"{scheduler.LABEL} was not installed.")
        else:
            state = scheduler.status()
            out(
                f"{scheduler.LABEL}: "
                f"{'loaded' if state.loaded else 'not loaded'}; "
                f"agent file {'present' if state.plist_exists else 'missing'}."
            )
    except scheduler.SchedulerError as error:
        out(str(error))
        return EXIT_SCHEDULE_ERROR
    return 0


def _tick(
    conn: sqlite3.Connection,
    specs: Sequence[JobSpec],
    fetcher: Optional[BarFetcher],
    clock: Callable[[], datetime],
    out: Callable[[str], None],
) -> int:
    if not specs:
        out("No jobs are registered yet.")
        return 0
    if fetcher is None:
        out("No bar source is configured, so no job ran.")
        return EXIT_NO_FETCHER
    results = tick(conn, specs, fetcher, clock=clock)
    if not results:
        out("No jobs are due.")
        return 0
    for result in results:
        if result.status == "skipped":
            out(f"{result.job_name}: skipped, a run is already in progress.")
        else:
            out(f"{result.job_name}: {result.status} ({result.items_failed} item(s) failed).")
    return 0


def _print_status(
    conn: sqlite3.Connection,
    specs: Sequence[JobSpec],
    now: datetime,
    out: Callable[[str], None],
) -> int:
    statuses = job_status(conn, now=now)
    if not statuses:
        out("No jobs have been scheduled yet.")
        return 0
    specs_by_name = {spec.name: spec for spec in specs}
    for status in statuses:
        out(_status_line(status))
        spec = specs_by_name.get(status.name)
        if spec is not None:
            cells = coverage(conn, spec, now=now, periods=COVERAGE_PERIODS)
            out("  coverage, newest first: " + ", ".join(f"{cell.period} {cell.status}" for cell in cells))
    return 0


def _status_line(status: JobStatus) -> str:
    line = (
        f"{status.name}: every {_interval_label(status.interval_seconds)}; "
        f"next run {status.next_run_at or 'now'}; "
        f"last success {status.last_success_at or 'never'}"
    )
    if status.progress is not None:
        line += (
            f"; latest run {status.latest_status}: "
            f"{status.progress.done}/{status.progress.total} done, {status.progress.failed} failed"
        )
    if status.overdue:
        line += "; OVERDUE, it has not run since it was due"
    return line


def _interval_label(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds}s"
