from datetime import timedelta

from data_jobs.runner import JobSpec, run_job
from data_jobs.store import connect
from data_jobs.telemetry import status_payload
from support import NOW, FakeFetcher, FixedClock

SPEC = JobSpec(name="gm-daily", interval=timedelta(days=1), symbols=("A", "B", "C"), timeframes=("1D",), bar_count=2)


def test_the_payload_reports_progress_errors_runs_and_coverage_for_a_partial_run():
    conn = connect(":memory:")
    run_job(conn, SPEC, FakeFetcher(failing=[("B", "1D")]), clock=FixedClock(NOW))

    (job,) = status_payload(conn, now=NOW)["jobs"]

    assert job["name"] == "gm-daily"
    assert job["latest_status"] == "partial"
    assert job["progress"] == {"total": 3, "done": 3, "failed": 1}
    assert job["last_full_success_at"] is None
    failed = [item for item in job["items"] if item["status"] == "failed"]
    assert [(item["symbol"], item["error"]) for item in failed] == [("B", "ConnectionError: source unreachable")]
    assert job["runs"][0]["bars_inserted"] == 4
    assert job["coverage"] == [{"period": "2026-10-22", "status": "partial"}]


def test_a_later_successful_retry_marks_the_period_succeeded_and_sets_the_full_success_time():
    conn = connect(":memory:")
    fetcher = FakeFetcher(failing=[("B", "1D")])
    run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))
    fetcher.failing.clear()
    run_job(conn, SPEC, fetcher, clock=FixedClock(NOW + timedelta(hours=1)))

    (job,) = status_payload(conn, now=NOW + timedelta(hours=1))["jobs"]

    assert job["coverage"] == [{"period": "2026-10-22", "status": "succeeded"}]
    assert job["last_full_success_at"] is not None
    assert job["latest_status"] == "succeeded"


def test_an_empty_database_has_no_jobs_yet():
    conn = connect(":memory:")

    assert status_payload(conn, now=NOW) == {"generated_at": "2026-10-22T12:00:00.000000Z", "jobs": []}
