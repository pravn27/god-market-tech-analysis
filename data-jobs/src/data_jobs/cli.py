"""Command line: run due jobs, show schedules, progress and coverage, and manage the launchd schedule."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Optional, Sequence

from . import scheduler, web
from .config import DEFAULT_DB, ENV_FILE, GOD_MARKET_SRC_DIR, LOG_DIR, SRC_DIR
from .registry import InstrumentListUnavailable, bar_source, registered_jobs
from .runner import BarFetcher, JobSpec, JobStatus, coverage, job_status, tick
from .store import connect, utc_now
from .web import DEFAULT_PORT

EXIT_SCHEDULE_ERROR = 1
EXIT_NO_FETCHER = 2
EXIT_NO_INSTRUMENTS = 3
COVERAGE_PERIODS = 7
# The Desktop watchlist read needs these. The scheduled run has no shell environment, so they are copied into the agent.
BRIDGE_ENV_KEYS = ("TRADINGVIEW_DESKTOP_BRIDGE_CLI", "TRADINGVIEW_DESKTOP_BRIDGE_NODE")


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
    page = commands.add_parser("ui", help="Serve the progress page (read-only) on http://127.0.0.1:8765.")
    page.add_argument("--host", default="127.0.0.1", help="Address to listen on (default: 127.0.0.1, this Mac only).")
    page.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port (default: {DEFAULT_PORT}).")
    schedule = commands.add_parser("schedule", help="Manage the macOS launchd agent that runs tick hourly.")
    actions = schedule.add_subparsers(dest="action", required=True)
    install = actions.add_parser("install", help="Install and load the agent, which runs now and then on the interval.")
    install.add_argument("--every-minutes", type=int, default=60, help="Interval between runs (default: 60).")
    actions.add_parser("uninstall", help="Unload the agent and delete its file.")
    actions.add_parser("status", help="Show whether the agent is installed and loaded.")
    args = parser.parse_args(argv)

    if args.command == "schedule":
        return _schedule(args, out)

    if args.command == "ui":
        return _ui(args, out)

    conn = connect(args.db)
    try:
        if args.command == "status":
            # Status works without Desktop: without the watchlist it only leaves out the coverage lines.
            current = specs if specs is not None else _registered_for_status(out)
            return _print_status(conn, current, clock(), out)
        if specs is None:
            specs = _registered_for_tick(out)
            if specs is None:
                return EXIT_NO_INSTRUMENTS
            if fetcher is None:
                fetcher = bar_source()
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
                environment=_bridge_environment(),
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


def _registered_for_tick(out: Callable[[str], None]) -> Optional[Sequence[JobSpec]]:
    try:
        return registered_jobs()
    except InstrumentListUnavailable as error:
        out(f"Instrument list unavailable, so no job ran: {error}")
        return None


def _registered_for_status(out: Callable[[str], None]) -> Sequence[JobSpec]:
    try:
        return registered_jobs()
    except InstrumentListUnavailable as error:
        out(f"Instrument list unavailable, so coverage is not shown: {error}")
        return ()


def _bridge_environment(env_file: Path = ENV_FILE) -> Dict[str, str]:
    """The Desktop bridge settings, from the shell environment or the app's ``.env.local``."""
    from_file: Dict[str, str] = {}
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.strip().partition("=")
            if separator and key.strip():
                from_file[key.strip()] = value.strip().strip("'\"")
    resolved = {key: os.environ.get(key) or from_file.get(key, "") for key in BRIDGE_ENV_KEYS}
    return {key: value for key, value in resolved.items() if value}


def _ui(args: argparse.Namespace, out: Callable[[str], None]) -> int:
    server = web.serve(Path(args.db), host=args.host, port=args.port)
    out(f"Data jobs page: http://{args.host}:{args.port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        out("Stopped.")
    finally:
        server.server_close()
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
