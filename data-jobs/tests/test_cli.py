from datetime import timedelta

from data_jobs import cli
from data_jobs.cli import main
from data_jobs.registry import InstrumentListUnavailable
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

    code = main(["--db", str(tmp_path / "jobs.sqlite3"), "status"], specs=(), out=out)

    assert code == 0
    assert lines == ["No jobs have been scheduled yet."]


def test_tick_with_no_registered_jobs_says_so(tmp_path):
    lines, out = _lines()

    code = main(["--db", str(tmp_path / "jobs.sqlite3"), "tick"], specs=(), out=out)

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
    main(["--db", db, "status"], specs=(SPEC,), clock=FixedClock(NOW), out=status_out)
    assert status_lines == [
        "gm-weekly: every 7d; next run 2026-10-29T12:00:00.000000Z; "
        "last success 2026-10-22T12:00:00.000000Z; latest run succeeded: 1/1 done, 0 failed",
        "  coverage, newest first: 2026-W43 succeeded, 2026-W42 missing, 2026-W41 missing, "
        "2026-W40 missing, 2026-W39 missing, 2026-W38 missing, 2026-W37 missing",
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


def test_tick_exits_3_and_runs_nothing_when_the_instrument_list_is_unavailable(tmp_path, monkeypatch):
    lines, out = _lines()

    def unavailable():
        raise InstrumentListUnavailable("TradingView Desktop is not open.")

    monkeypatch.setattr(cli, "registered_jobs", unavailable)

    code = main(["--db", str(tmp_path / "jobs.sqlite3"), "tick"], out=out)

    assert code == 3
    assert lines == ["Instrument list unavailable, so no job ran: TradingView Desktop is not open."]


def test_status_still_shows_jobs_when_the_instrument_list_is_unavailable(tmp_path, monkeypatch):
    lines, out = _lines()

    def unavailable():
        raise InstrumentListUnavailable("TradingView Desktop is not open.")

    monkeypatch.setattr(cli, "registered_jobs", unavailable)

    code = main(["--db", str(tmp_path / "jobs.sqlite3"), "status"], out=out)

    assert code == 0
    assert lines[0] == (
        "Instrument list unavailable, so coverage is not shown: TradingView Desktop is not open."
    )


def test_bridge_settings_come_from_the_env_file_unless_the_shell_overrides_them(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "# local settings\n"
        "TRADINGVIEW_DESKTOP_BRIDGE_CLI='/opt/bridge/src/cli/index.js'\n"
        "TRADINGVIEW_DESKTOP_BRIDGE_NODE=/usr/local/bin/node\n"
        "GLOBAL_MARKET_LIVE_ENABLED=true\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TRADINGVIEW_DESKTOP_BRIDGE_CLI", raising=False)
    monkeypatch.delenv("TRADINGVIEW_DESKTOP_BRIDGE_NODE", raising=False)

    assert cli._bridge_environment(env_file) == {
        "TRADINGVIEW_DESKTOP_BRIDGE_CLI": "/opt/bridge/src/cli/index.js",
        "TRADINGVIEW_DESKTOP_BRIDGE_NODE": "/usr/local/bin/node",
    }

    monkeypatch.setenv("TRADINGVIEW_DESKTOP_BRIDGE_NODE", "/opt/node")
    assert cli._bridge_environment(env_file)["TRADINGVIEW_DESKTOP_BRIDGE_NODE"] == "/opt/node"
