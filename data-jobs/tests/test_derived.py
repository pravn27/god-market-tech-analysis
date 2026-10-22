from datetime import timedelta

import pytest

from data_jobs.runner import JobSpec, run_job
from data_jobs.store import connect, to_text
from support import NOW, UTC, FakeFetcher, FixedClock, bar
from datetime import datetime

# Mon 5 Oct 2026 to Thu 22 Oct 2026. Monday 5 Oct starts a week, and 1 Oct starts the month.
SPEC = JobSpec(
    name="gm-daily",
    interval=timedelta(days=1),
    symbols=("DJI",),
    timeframes=("1D",),
    bar_count=30,
    derived_periods=("1W",),
)


def _stored(conn, timeframe):
    return conn.execute(
        "SELECT bar_time, open, high, low, close, volume, is_closed, source FROM bars "
        "WHERE symbol = 'DJI' AND timeframe = ? ORDER BY bar_time",
        (timeframe,),
    ).fetchall()


def _day(day):
    return to_text(datetime(2026, 10, day, tzinfo=UTC))


def test_weekly_bars_are_built_from_the_stored_daily_bars_and_marked_by_source():
    conn = connect(":memory:")
    days = [bar(day, close=100 + day) for day in range(5, 23)]
    fetcher = FakeFetcher({("DJI", "1D"): days}, source="official_mcp")

    result = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))

    assert result.status == "succeeded"
    weekly = _stored(conn, "1W")
    assert [row["bar_time"] for row in weekly] == [_day(5), _day(12), _day(19)]
    first_week = weekly[0]
    # Week of 5 Oct: open of Monday, close of Sunday's last stored bar (11 Oct), high and low across the days.
    assert first_week["open"] == 99.0
    assert first_week["close"] == 111.0
    assert first_week["high"] == max(bar(day, close=100 + day).high for day in range(5, 12))
    assert first_week["low"] == 98.0
    assert [row["is_closed"] for row in weekly] == [1, 1, 0]  # the week of 19 Oct has not ended
    assert {row["source"] for row in weekly} == {"derived"}
    assert {row["source"] for row in _stored(conn, "1D")} == {"official_mcp"}


def test_a_period_that_starts_before_the_stored_history_is_not_stored():
    conn = connect(":memory:")
    # History starts on Wednesday 7 Oct, so the week that began on Monday 5 Oct is incomplete.
    days = [bar(day) for day in range(7, 23)]
    fetcher = FakeFetcher({("DJI", "1D"): days})

    run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))

    assert [row["bar_time"] for row in _stored(conn, "1W")] == [_day(12), _day(19)]


def test_monthly_and_quarterly_bars_wait_for_history_that_covers_the_whole_period():
    conn = connect(":memory:")
    spec = JobSpec(
        name="gm-daily",
        interval=timedelta(days=1),
        symbols=("DJI",),
        timeframes=("1D",),
        bar_count=30,
        derived_periods=("1M", "3M"),
    )
    days = [bar(day) for day in range(5, 23)]

    run_job(conn, spec, FakeFetcher({("DJI", "1D"): days}), clock=FixedClock(NOW))

    # October starts on 1 Oct and only 5 Oct is stored, so the October bar is held back.
    assert _stored(conn, "1M") == []
    assert _stored(conn, "3M") == []


def test_derived_bars_count_toward_the_run_totals():
    conn = connect(":memory:")
    days = [bar(day) for day in range(5, 23)]

    result = run_job(conn, SPEC, FakeFetcher({("DJI", "1D"): days}), clock=FixedClock(NOW))

    run = conn.execute("SELECT * FROM job_runs WHERE id = ?", (result.run_id,)).fetchone()
    assert run["bars_inserted"] == 18 + 3  # 18 daily bars, then 3 weekly bars


def test_a_second_run_updates_the_forming_week_as_new_days_arrive():
    conn = connect(":memory:")
    first = [bar(day, close=100) for day in range(5, 22)]
    run_job(conn, SPEC, FakeFetcher({("DJI", "1D"): first}), clock=FixedClock(NOW))

    # The next day's run brings Thursday 22 Oct, which closes at 150 and so moves the open week's close.
    later = [bar(day, close=100) for day in range(5, 22)] + [bar(22, close=150)]
    result = run_job(
        conn,
        SPEC,
        FakeFetcher({("DJI", "1D"): later}),
        clock=FixedClock(NOW + timedelta(days=1)),
    )

    assert result.status == "succeeded"
    assert _stored(conn, "1W")[-1]["close"] == 150.0


def test_derived_periods_must_be_known_and_need_daily_bars():
    with pytest.raises(ValueError, match="Unsupported derived period"):
        JobSpec(
            name="x",
            interval=timedelta(days=1),
            symbols=("DJI",),
            timeframes=("1D",),
            bar_count=5,
            derived_periods=("2W",),
        )
    with pytest.raises(ValueError, match="must fetch 1D"):
        JobSpec(
            name="x",
            interval=timedelta(days=1),
            symbols=("DJI",),
            timeframes=("1H",),
            bar_count=5,
            derived_periods=("1W",),
        )
