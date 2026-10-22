from datetime import timedelta

import pytest

from data_jobs.fallback import DESKTOP_SOURCE, FallbackFetcher, QuotaExhaustedError
from data_jobs.runner import FetchResult, JobSpec, job_status, run_job
from data_jobs.store import connect
from support import NOW, FixedClock, bar


class QuotaLimitedMcp:
    """Stands in for the official MCP: quota exhausted for the symbols listed, otherwise normal bars."""

    source = "official_mcp"

    def __init__(self, exhausted=()):
        self.exhausted = set(exhausted)
        self.calls = 0

    def fetch(self, symbol, timeframe, *, count):
        self.calls += 1
        if symbol in self.exhausted:
            raise QuotaExhaustedError("TradingView MCP daily quota is used up; it resets at 00:00 UTC.")
        return FetchResult(bars=[bar(19), bar(20)], source=self.source)


class FakeDesktop:
    def __init__(self, *, open_=True):
        self.open_ = open_
        self.reads = []

    def is_open(self):
        return self.open_

    def read_daily(self, symbol, *, count, now):
        self.reads.append((symbol, count))
        return [bar(21, close=101.0), bar(22, close=102.0, is_closed=False)]


def test_the_mcp_answers_when_it_can_and_the_desktop_is_not_touched():
    desktop = FakeDesktop()
    fetcher = FallbackFetcher(QuotaLimitedMcp(), desktop)

    result = fetcher.fetch("DJI", "1D", count=2)

    assert result.source == "official_mcp"
    assert desktop.reads == []


def test_a_quota_error_falls_back_to_the_desktop_daily_bars_and_labels_them():
    desktop = FakeDesktop()
    fetcher = FallbackFetcher(QuotaLimitedMcp(exhausted={"DJI"}), desktop)

    result = fetcher.fetch("DJI", "1D", count=2)

    assert result.source == DESKTOP_SOURCE
    assert [b.close for b in result.bars] == [101.0, 102.0]
    assert desktop.reads == [("DJI", 2)]
    assert fetcher.desktop_reads == 1


def test_other_mcp_failures_are_not_treated_as_a_quota_problem():
    class BrokenMcp:
        def fetch(self, symbol, timeframe, *, count):
            raise ConnectionError("network down")

    desktop = FakeDesktop()
    fetcher = FallbackFetcher(BrokenMcp(), desktop)

    with pytest.raises(ConnectionError):
        fetcher.fetch("DJI", "1D", count=2)
    assert desktop.reads == []


def test_when_the_desktop_is_not_open_the_item_fails_with_the_quota_reason():
    desktop = FakeDesktop(open_=False)
    fetcher = FallbackFetcher(QuotaLimitedMcp(exhausted={"DJI"}), desktop)

    with pytest.raises(QuotaExhaustedError, match="not open and responding"):
        fetcher.fetch("DJI", "1D", count=2)
    assert desktop.reads == []


def test_intraday_and_weekly_items_never_use_the_desktop_chart():
    desktop = FakeDesktop()
    fetcher = FallbackFetcher(QuotaLimitedMcp(exhausted={"DJI"}), desktop)

    for timeframe in ("1W", "4H"):
        with pytest.raises(QuotaExhaustedError, match="Only daily bars"):
            fetcher.fetch("DJI", timeframe, count=2)
    assert desktop.reads == []


def test_the_desktop_read_budget_stops_the_fallback_for_the_rest_of_the_run():
    desktop = FakeDesktop()
    fetcher = FallbackFetcher(QuotaLimitedMcp(exhausted={"A", "B", "C"}), desktop, budget=2)

    fetcher.fetch("A", "1D", count=2)
    fetcher.fetch("B", "1D", count=2)
    with pytest.raises(QuotaExhaustedError, match="limit of 2 for this run is used up"):
        fetcher.fetch("C", "1D", count=2)
    assert len(desktop.reads) == 2


def test_a_negative_budget_is_rejected():
    with pytest.raises(ValueError):
        FallbackFetcher(QuotaLimitedMcp(), FakeDesktop(), budget=-1)


def test_a_run_stores_each_bar_with_the_source_it_came_from():
    conn = connect(":memory:")
    spec = JobSpec(
        name="gm-daily",
        interval=timedelta(days=1),
        symbols=("DJI", "SPX"),
        timeframes=("1D",),
        bar_count=2,
    )
    fetcher = FallbackFetcher(QuotaLimitedMcp(exhausted={"DJI"}), FakeDesktop())

    result = run_job(conn, spec, fetcher, clock=FixedClock(NOW))

    rows = conn.execute("SELECT symbol, source, is_closed FROM bars ORDER BY symbol, bar_time").fetchall()
    assert [(row["symbol"], row["source"]) for row in rows] == [
        ("DJI", DESKTOP_SOURCE),
        ("DJI", DESKTOP_SOURCE),
        ("SPX", "official_mcp"),
        ("SPX", "official_mcp"),
    ]
    assert result.status == "succeeded"
    assert job_status(conn, now=NOW)[0].progress.failed == 0


def test_a_quota_failure_with_no_desktop_is_recorded_as_a_failed_item():
    conn = connect(":memory:")
    spec = JobSpec(name="gm-daily", interval=timedelta(days=1), symbols=("DJI",), timeframes=("1D",), bar_count=2)
    fetcher = FallbackFetcher(QuotaLimitedMcp(exhausted={"DJI"}), FakeDesktop(open_=False))

    result = run_job(conn, spec, fetcher, clock=FixedClock(NOW))

    assert result.status == "failed"
    error = conn.execute("SELECT error FROM job_items").fetchone()[0]
    assert "QuotaExhaustedError" in error
    assert "not open and responding" in error
