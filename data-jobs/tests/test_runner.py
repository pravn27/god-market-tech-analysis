from datetime import datetime, timedelta

from data_jobs.runner import (
    FAILED,
    MISSING,
    PARTIAL,
    PENDING,
    SKIPPED,
    SUCCEEDED,
    JobSpec,
    PeriodCoverage,
    coverage,
    daily_key,
    job_status,
    run_job,
    tick,
    weekly_key,
)
from data_jobs.store import connect, to_text
from support import NOW, UTC, FakeFetcher, FixedClock

SPEC = JobSpec(
    name="gm-weekly",
    interval=timedelta(days=7),
    symbols=("DJI", "SPX"),
    timeframes=("1W",),
    bar_count=4,
    period_key=weekly_key,
)

DAILY = JobSpec(
    name="gm-daily",
    interval=timedelta(days=1),
    symbols=("DJI",),
    timeframes=("1D",),
    bar_count=2,
)


def _run_row(conn, run_id):
    return conn.execute("SELECT * FROM job_runs WHERE id = ?", (run_id,)).fetchone()


def _bar_count(conn):
    return conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0]


def _status(conn, now=NOW):
    return job_status(conn, now=now)[0]


def test_a_clean_run_stores_bars_records_progress_and_schedules_the_next_run():
    conn = connect(":memory:")
    fetcher = FakeFetcher()

    result = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))

    assert result.status == SUCCEEDED
    assert _bar_count(conn) == 4
    assert fetcher.calls == [("DJI", "1W", 4), ("SPX", "1W", 4)]
    status = _status(conn)
    assert (status.progress.done, status.progress.total, status.progress.failed) == (2, 2, 0)
    assert status.next_run_at == to_text(NOW + timedelta(days=7))
    assert status.last_success_at == to_text(NOW)
    assert status.overdue is False


def test_running_again_with_the_same_data_changes_no_bars():
    conn = connect(":memory:")
    first = run_job(conn, SPEC, FakeFetcher(), clock=FixedClock(NOW))
    second = run_job(conn, SPEC, FakeFetcher(), clock=FixedClock(NOW + timedelta(days=7)))

    first_row = _run_row(conn, first.run_id)
    second_row = _run_row(conn, second.run_id)
    assert (first_row["bars_inserted"], first_row["bars_unchanged"]) == (4, 0)
    assert (second_row["bars_inserted"], second_row["bars_updated"], second_row["bars_unchanged"]) == (0, 0, 4)
    assert _bar_count(conn) == 4


def test_one_failed_symbol_makes_the_run_partial_and_keeps_the_rest():
    conn = connect(":memory:")
    fetcher = FakeFetcher(failing=[("SPX", "1W")])

    result = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))

    assert result.status == PARTIAL
    assert result.items_failed == 1
    assert _bar_count(conn) == 2
    status = _status(conn)
    assert (status.progress.done, status.progress.failed) == (2, 1)
    assert status.last_success_at is None
    assert status.next_run_at == to_text(NOW + timedelta(days=7))
    error = conn.execute("SELECT error FROM job_items WHERE symbol = 'SPX'").fetchone()[0]
    assert "source unreachable" in error


def test_a_run_where_everything_fails_retries_in_an_hour():
    conn = connect(":memory:")
    fetcher = FakeFetcher(failing=[("DJI", "1W"), ("SPX", "1W")])

    result = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))

    assert result.status == FAILED
    assert _status(conn).next_run_at == to_text(NOW + timedelta(hours=1))


def test_an_empty_answer_from_the_source_counts_as_a_failed_item():
    conn = connect(":memory:")
    fetcher = FakeFetcher(bars={("SPX", "1W"): []})

    result = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))

    assert result.status == PARTIAL
    error = conn.execute("SELECT error FROM job_items WHERE symbol = 'SPX'").fetchone()[0]
    assert "no bars" in error


def test_tick_runs_only_jobs_that_are_due():
    conn = connect(":memory:")
    fetcher = FakeFetcher()

    assert len(tick(conn, [SPEC], fetcher, clock=FixedClock(NOW))) == 1
    assert tick(conn, [SPEC], fetcher, clock=FixedClock(NOW + timedelta(days=1))) == []
    assert len(tick(conn, [SPEC], fetcher, clock=FixedClock(NOW + timedelta(days=7)))) == 1


def test_a_run_already_in_progress_blocks_a_second_start():
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, period_key, status, started_at, heartbeat_at, items_total) "
        "VALUES (?, '2026-W43', 'running', ?, ?, 2)",
        (SPEC.name, to_text(NOW), to_text(NOW)),
    )
    fetcher = FakeFetcher()

    result = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW + timedelta(minutes=1)))

    assert result.status == SKIPPED
    assert result.run_id is None
    assert fetcher.calls == []


def test_a_run_with_an_old_heartbeat_is_marked_stalled_and_the_job_restarts():
    conn = connect(":memory:")
    conn.execute(
        "INSERT INTO job_runs (job_name, period_key, status, started_at, heartbeat_at, items_total) "
        "VALUES (?, '2026-W43', 'running', ?, ?, 2)",
        (SPEC.name, to_text(NOW - timedelta(hours=2)), to_text(NOW - timedelta(hours=1))),
    )

    result = run_job(conn, SPEC, FakeFetcher(), clock=FixedClock(NOW))

    assert result.status == SUCCEEDED
    old = conn.execute("SELECT status FROM job_runs WHERE id = 1").fetchone()[0]
    assert old == "stalled"


def test_periods_are_utc_dates_and_iso_weeks():
    assert daily_key(NOW) == "2026-10-22"
    assert weekly_key(NOW) == "2026-W43"
    # ISO weeks run Monday to Sunday, so Sunday 25 October is still week 43 and Monday 26 starts week 44.
    assert weekly_key(datetime(2026, 10, 25, 23, tzinfo=UTC)) == "2026-W43"
    assert weekly_key(datetime(2026, 10, 26, 0, tzinfo=UTC)) == "2026-W44"


def test_each_run_is_stamped_with_its_period():
    conn = connect(":memory:")
    result = run_job(conn, SPEC, FakeFetcher(), clock=FixedClock(NOW))

    assert _run_row(conn, result.run_id)["period_key"] == "2026-W43"


def test_coverage_marks_a_missed_day_as_missing_and_today_as_pending():
    conn = connect(":memory:")
    run_job(conn, DAILY, FakeFetcher(), clock=FixedClock(datetime(2026, 10, 20, 12, tzinfo=UTC)))
    run_job(conn, DAILY, FakeFetcher(), clock=FixedClock(datetime(2026, 10, 22, 12, tzinfo=UTC)))

    cells = coverage(conn, DAILY, now=datetime(2026, 10, 22, 13, tzinfo=UTC), periods=3)
    assert [(cell.period, cell.status) for cell in cells] == [
        ("2026-10-22", SUCCEEDED),
        ("2026-10-21", MISSING),
        ("2026-10-20", SUCCEEDED),
    ]

    cells = coverage(conn, DAILY, now=datetime(2026, 10, 23, 6, tzinfo=UTC), periods=2)
    assert cells[0] == PeriodCoverage(period="2026-10-23", status=PENDING)
    assert cells[1] == PeriodCoverage(period="2026-10-22", status=SUCCEEDED)


def test_a_period_with_a_failed_run_then_a_successful_retry_counts_as_succeeded():
    conn = connect(":memory:")
    morning = datetime(2026, 10, 22, 9, tzinfo=UTC)
    run_job(conn, DAILY, FakeFetcher(failing=[("DJI", "1D")]), clock=FixedClock(morning))
    run_job(conn, DAILY, FakeFetcher(), clock=FixedClock(morning + timedelta(hours=1)))

    cells = coverage(conn, DAILY, now=morning + timedelta(hours=2), periods=1)
    assert cells[0].status == SUCCEEDED


def test_a_period_with_only_failed_runs_shows_the_failure():
    conn = connect(":memory:")
    run_job(conn, DAILY, FakeFetcher(failing=[("DJI", "1D")]), clock=FixedClock(NOW))

    cells = coverage(conn, DAILY, now=NOW, periods=1)
    assert cells[0].status == FAILED


def test_a_job_is_overdue_only_after_the_grace_period_past_its_due_time():
    conn = connect(":memory:")
    run_job(conn, SPEC, FakeFetcher(), clock=FixedClock(NOW))
    due = NOW + timedelta(days=7)

    assert _status(conn, now=due + timedelta(hours=1)).overdue is False
    assert _status(conn, now=due + timedelta(hours=3)).overdue is True


def test_a_job_that_has_started_is_not_overdue_even_past_due():
    conn = connect(":memory:")
    run_job(conn, SPEC, FakeFetcher(), clock=FixedClock(NOW))
    conn.execute(
        "INSERT INTO job_runs (job_name, period_key, status, started_at, heartbeat_at, items_total) "
        "VALUES (?, '2026-W44', 'running', ?, ?, 2)",
        (SPEC.name, to_text(NOW + timedelta(days=7, hours=3)), to_text(NOW + timedelta(days=7, hours=3))),
    )

    assert _status(conn, now=NOW + timedelta(days=7, hours=3)).overdue is False
