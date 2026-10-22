"""What the telemetry page shows: each job's schedule, the latest run's progress, recent runs and coverage.

Read-only. It only selects from the job tables and never creates or changes a row.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Dict, List

from .runner import job_status
from .store import to_text

RECENT_RUNS = 10
RECENT_PERIODS = 7


def status_payload(conn: sqlite3.Connection, *, now: datetime) -> Dict[str, Any]:
    return {
        "generated_at": to_text(now),
        "jobs": [_job(conn, status, now) for status in job_status(conn, now=now)],
    }


def _job(conn: sqlite3.Connection, status, now: datetime) -> Dict[str, Any]:
    runs = [
        dict(row)
        for row in conn.execute(
            "SELECT id, status, period_key, started_at, finished_at, items_total, "
            "bars_inserted, bars_updated, bars_unchanged FROM job_runs WHERE job_name = ? "
            "ORDER BY id DESC LIMIT ?",
            (status.name, RECENT_RUNS),
        )
    ]
    items: List[Dict[str, Any]] = []
    if status.latest_run_id is not None:
        items = [
            dict(row)
            for row in conn.execute(
                "SELECT symbol, timeframe, status, fetched_at, error FROM job_items "
                "WHERE run_id = ? ORDER BY rowid",
                (status.latest_run_id,),
            )
        ]
    return {
        "name": status.name,
        "interval_seconds": status.interval_seconds,
        "next_run_at": status.next_run_at,
        # Set only by a run that fully succeeded. A partial run does not move it.
        "last_full_success_at": status.last_success_at,
        "overdue": status.overdue,
        "latest_status": status.latest_status,
        "progress": (
            {"total": status.progress.total, "done": status.progress.done, "failed": status.progress.failed}
            if status.progress is not None
            else None
        ),
        "runs": runs,
        "items": items,
        "coverage": _coverage(conn, status.name),
    }


def _coverage(conn: sqlite3.Connection, job_name: str) -> List[Dict[str, str]]:
    """Newest period first. A period shows succeeded if any of its runs succeeded, else its latest run."""
    by_period: Dict[str, List[str]] = {}
    for row in conn.execute(
        "SELECT period_key, status FROM job_runs WHERE job_name = ? ORDER BY id DESC", (job_name,)
    ):
        by_period.setdefault(row["period_key"], []).append(row["status"])
    result = []
    for period, statuses in list(by_period.items())[:RECENT_PERIODS]:
        state = "succeeded" if "succeeded" in statuses else statuses[0]
        result.append({"period": period, "status": state})
    return result
