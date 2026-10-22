from datetime import timedelta

from data_jobs.cli import main
from data_jobs.runner import JobSpec, weekly_key
from support import NOW, FakeFetcher, FixedClock

SPEC = JobSpec(
    name="gm-weekly",
    interval=timedelta(days=7),
    symbols=("DJI",),
    timeframes=("1W",),
    bar_count=4,
    period_key=weekly_key,
)


def _lines():
    collected = []
    return collected, collected.append


def test_status_with_no_jobs_says_so(tmp_path):
    lines, out = _lines()

    code = main(["--db", str(tmp_path / "jobs.sqlite3"), "status"], out=out)

    assert code == 0
    assert lines == ["No jobs have been scheduled yet."]


def test_tick_with_no_registered_jobs_says_so(tmp_path):
    lines, out = _lines()

    code = main(["--db", str(tmp_path / "jobs.sqlite3"), "tick"], out=out)

    assert code == 0
    assert lines == ["No jobs are registered yet."]


def test_tick_without_a_bar_source_exits_with_an_error(tmp_path):
    lines, out = _lines()

    code = main(["--db", str(tmp_path / "jobs.sqlite3"), "tick"], specs=(SPEC,), out=out)

    assert code == 2
    assert "No bar source is configured" in lines[0]


def test_tick_runs_the_due_job_and_status_shows_its_progress(tmp_path):
    db = str(tmp_path / "jobs.sqlite3")
    lines, out = _lines()

    code = main(
        ["--db", db, "tick"],
        specs=(SPEC,),
        fetcher=FakeFetcher(),
        clock=FixedClock(NOW),
        out=out,
    )
    assert code == 0
    assert lines == ["gm-weekly: succeeded (0 item(s) failed)."]

    status_lines, status_out = _lines()
    main(["--db", db, "status"], clock=FixedClock(NOW), out=status_out)
    assert status_lines == [
        "gm-weekly: every 7d; next run 2026-10-29T12:00:00.000000Z; "
        "last success 2026-10-22T12:00:00.000000Z; latest run succeeded: 1/1 done, 0 failed"
    ]


def test_status_flags_overdue_jobs_and_shows_period_coverage(tmp_path):
    db = str(tmp_path / "jobs.sqlite3")
    main(["--db", db, "tick"], specs=(SPEC,), fetcher=FakeFetcher(), clock=FixedClock(NOW), out=lambda _: None)

    lines, out = _lines()
    main(
        ["--db", db, "status"],
        specs=(SPEC,),
        clock=FixedClock(NOW + timedelta(days=7, hours=3)),
        out=out,
    )

    assert "OVERDUE" in lines[0]
    assert "2026-W44 pending" in lines[1]
    assert "2026-W43 succeeded" in lines[1]
