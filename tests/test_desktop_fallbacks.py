"""Tests for the TradingView Desktop fallbacks used when the official MCP cannot provide data."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from god_market_api.desktop_candles import DesktopChartCandleProvider, FallbackChartProvider
from god_market_api.global_market import (
    RECORDED_WATCHLIST_GROUPS,
    WATCHLIST_ORIGIN_DESKTOP,
    WatchlistRead,
    WatchlistUnavailableError,
)
from god_market_api.models import Candle, ChartContext, DataSource, SourceState
from god_market_api.providers import DataSourceUnavailableError
from god_market_api.watchlist_source import (
    DesktopWatchlistSectionSource,
    FallbackWatchlistSource,
    parse_bridge_sequence,
)


NOW = datetime(2026, 10, 17, 8, 0, tzinfo=timezone.utc)


def _recorded_sequence() -> list[dict]:
    sequence: list[dict] = []
    for group in RECORDED_WATCHLIST_GROUPS:
        sequence.append({"section": group.name})
        sequence.extend({"symbol": item.symbol} for item in group.instruments)
    return sequence


class FakeReader:
    def __init__(self, payload=None, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error

    async def watchlist_payload(self):
        if self.error is not None:
            raise self.error
        return self.payload


class StaticSource:
    def __init__(self, result=None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    async def read(self) -> WatchlistRead:
        if self.error is not None:
            raise self.error
        return self.result


def _live_read(error: str | None = None) -> WatchlistRead:
    return WatchlistRead(groups=RECORDED_WATCHLIST_GROUPS, read_at=NOW, error=error)


def test_bridge_sequence_becomes_the_same_sections_the_mcp_gives() -> None:
    groups = parse_bridge_sequence({"success": True, "sequence": _recorded_sequence()})

    assert [group.name for group in groups] == [group.name for group in RECORDED_WATCHLIST_GROUPS]
    assert [item.symbol for group in groups for item in group.instruments] == [
        item.symbol for group in RECORDED_WATCHLIST_GROUPS for item in group.instruments
    ]


def test_bridge_sequence_rejects_failed_or_missing_output() -> None:
    with pytest.raises(WatchlistUnavailableError):
        parse_bridge_sequence({"success": False})
    with pytest.raises(WatchlistUnavailableError):
        parse_bridge_sequence({"success": True, "symbols": []})


def test_desktop_section_source_rejects_a_watchlist_that_is_not_ps_global_indices() -> None:
    foreign = {"success": True, "sequence": [{"section": "ALPHA"}, {"symbol": "NASDAQ:AAPL"}, {"symbol": "NASDAQ:MSFT"}]}
    source = DesktopWatchlistSectionSource(FakeReader(payload=foreign), clock=lambda: NOW)

    with pytest.raises(WatchlistUnavailableError, match="not PS_Global_Indices"):
        asyncio.run(source.read())


def test_desktop_section_source_accepts_the_watchlist_and_marks_the_origin() -> None:
    source = DesktopWatchlistSectionSource(
        FakeReader(payload={"success": True, "sequence": _recorded_sequence()}), clock=lambda: NOW
    )

    read = asyncio.run(source.read())

    assert read.origin == WATCHLIST_ORIGIN_DESKTOP
    assert read.read_at == NOW
    assert read.error is None


def test_desktop_section_source_turns_bridge_errors_into_unavailable() -> None:
    source = DesktopWatchlistSectionSource(FakeReader(error=DataSourceUnavailableError("CDP is down")))

    with pytest.raises(WatchlistUnavailableError, match="CDP is down"):
        asyncio.run(source.read())


def test_watchlist_uses_the_official_mcp_when_it_is_live() -> None:
    desktop = StaticSource(result=_live_read())
    chain = FallbackWatchlistSource(StaticSource(result=_live_read()), desktop)

    read = asyncio.run(chain.read())

    assert read.origin == "official_mcp"
    assert read.error is None


def test_watchlist_uses_the_desktop_when_the_mcp_read_fails() -> None:
    desktop_read = WatchlistRead(groups=RECORDED_WATCHLIST_GROUPS, read_at=NOW, origin=WATCHLIST_ORIGIN_DESKTOP)
    chain = FallbackWatchlistSource(
        StaticSource(error=WatchlistUnavailableError("MCP session expired")), StaticSource(result=desktop_read)
    )

    read = asyncio.run(chain.read())

    assert read.origin == WATCHLIST_ORIGIN_DESKTOP
    assert read.error == "MCP session expired"


def test_watchlist_prefers_desktop_over_a_stale_mcp_reading() -> None:
    desktop_read = WatchlistRead(groups=RECORDED_WATCHLIST_GROUPS, read_at=NOW, origin=WATCHLIST_ORIGIN_DESKTOP)
    stale_mcp = WatchlistRead(groups=RECORDED_WATCHLIST_GROUPS, read_at=NOW - timedelta(hours=1), error="MCP down")
    chain = FallbackWatchlistSource(StaticSource(result=stale_mcp), StaticSource(result=desktop_read))

    read = asyncio.run(chain.read())

    assert read.origin == WATCHLIST_ORIGIN_DESKTOP
    assert read.error == "MCP down"


def test_watchlist_keeps_the_stale_mcp_reading_when_the_desktop_also_fails() -> None:
    stale_mcp = WatchlistRead(groups=RECORDED_WATCHLIST_GROUPS, read_at=NOW - timedelta(hours=1), error="MCP down")
    chain = FallbackWatchlistSource(
        StaticSource(result=stale_mcp), StaticSource(error=WatchlistUnavailableError("CDP is down"))
    )

    assert asyncio.run(chain.read()) is stale_mcp


def test_watchlist_raises_when_nothing_can_be_read() -> None:
    chain = FallbackWatchlistSource(
        StaticSource(error=WatchlistUnavailableError("MCP down")),
        StaticSource(error=WatchlistUnavailableError("CDP is down")),
    )

    with pytest.raises(WatchlistUnavailableError, match="MCP down Desktop fallback: CDP is down"):
        asyncio.run(chain.read())


class FakeChart:
    """Simulates one TradingView Desktop chart: the bridge reads and changes the chart on screen."""

    def __init__(self, symbol: str, resolution: str, *, fail_ohlcv: bool = False) -> None:
        self.symbol = symbol
        self.resolution = resolution
        self.fail_ohlcv = fail_ohlcv
        self.calls: list[tuple[str, ...]] = []

    async def run(self, *args: str):
        self.calls.append(args)
        if args == ("state",):
            return {"success": True, "symbol": self.symbol, "resolution": self.resolution}
        if args[0] == "symbol":
            self.symbol = args[1]
            return {"success": True, "symbol": self.symbol}
        if args[0] == "timeframe":
            self.resolution = args[1]
            return {"success": True, "resolution": self.resolution}
        if args[0] == "ohlcv":
            if self.fail_ohlcv:
                raise DataSourceUnavailableError("The bridge could not read bars.")
            return {
                "success": True,
                "bars": [
                    {"time": 1791938700 + index * 3600, "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10}
                    for index in range(3)
                ],
            }
        raise AssertionError(f"unexpected bridge call {args}")


async def _no_sleep(_seconds: float) -> None:
    return None


def test_chart_is_switched_read_and_restored_to_what_the_user_had_open() -> None:
    chart = FakeChart("NSEIX:NIFTY1!", "1D")
    provider = DesktopChartCandleProvider(chart, sleep=_no_sleep, clock=lambda: NOW)

    context = asyncio.run(provider.get_chart_context("TVC:SILVER", "1h"))

    assert context.source is DataSource.DESKTOP_BRIDGE
    assert context.timeframe == "1h"
    assert context.freshness_state is SourceState.READY
    assert len(context.candles) == 3
    assert chart.symbol == "NSEIX:NIFTY1!"
    assert chart.resolution == "1D"
    assert ("symbol", "TVC:SILVER") in chart.calls
    assert ("timeframe", "60") in chart.calls


def test_chart_is_restored_even_when_the_bars_cannot_be_read() -> None:
    chart = FakeChart("NSEIX:NIFTY1!", "1D", fail_ohlcv=True)
    provider = DesktopChartCandleProvider(chart, sleep=_no_sleep, clock=lambda: NOW)

    with pytest.raises(DataSourceUnavailableError, match="could not read bars"):
        asyncio.run(provider.get_chart_context("TVC:SILVER", "1h"))

    assert (chart.symbol, chart.resolution) == ("NSEIX:NIFTY1!", "1D")


def test_recent_candles_are_reused_without_touching_the_chart() -> None:
    clock = {"now": NOW}
    chart = FakeChart("NSEIX:NIFTY1!", "1D")
    provider = DesktopChartCandleProvider(
        chart, sleep=_no_sleep, clock=lambda: clock["now"], cache_for=timedelta(seconds=120)
    )
    asyncio.run(provider.get_chart_context("TVC:SILVER", "1h"))
    calls_after_first = len(chart.calls)

    clock["now"] = NOW + timedelta(seconds=60)
    asyncio.run(provider.get_chart_context("TVC:SILVER", "1h"))
    assert len(chart.calls) == calls_after_first

    clock["now"] = NOW + timedelta(seconds=121)
    asyncio.run(provider.get_chart_context("TVC:SILVER", "1h"))
    assert len(chart.calls) > calls_after_first


def test_an_unsupported_timeframe_is_rejected_before_the_chart_is_touched() -> None:
    chart = FakeChart("NSEIX:NIFTY1!", "1D")
    provider = DesktopChartCandleProvider(chart, sleep=_no_sleep, clock=lambda: NOW)

    with pytest.raises(DataSourceUnavailableError, match="Unsupported timeframe"):
        asyncio.run(provider.get_chart_context("TVC:SILVER", "2h"))
    assert chart.calls == []


class StaticChart:
    def __init__(self, result: ChartContext | None = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        if self.error is not None:
            raise self.error
        return self.result


def _context(source: DataSource = DataSource.DESKTOP_BRIDGE) -> ChartContext:
    candles = [
        Candle(timestamp=NOW - timedelta(hours=1), open=1, high=1, low=1, close=1),
        Candle(timestamp=NOW, open=2, high=2, low=2, close=2),
    ]
    return ChartContext(
        symbol="TVC:SILVER",
        timeframe="1h",
        source=source,
        source_timestamp=NOW,
        freshness_state=SourceState.READY,
        candles=candles,
    )


def test_mtf_fallback_uses_the_desktop_chart_and_says_why() -> None:
    provider = FallbackChartProvider(
        StaticChart(error=DataSourceUnavailableError("MCP rate limited")), StaticChart(result=_context())
    )

    context = asyncio.run(provider.get_chart_context("TVC:SILVER", "1h"))

    assert context.source is DataSource.DESKTOP_BRIDGE
    assert context.warnings[0] == (
        "Official TradingView MCP was unavailable (MCP rate limited); candles were read from TradingView Desktop."
    )


def test_mtf_fallback_reports_both_reasons_when_neither_source_works() -> None:
    provider = FallbackChartProvider(
        StaticChart(error=DataSourceUnavailableError("MCP rate limited")),
        StaticChart(error=DataSourceUnavailableError("CDP is down")),
    )

    with pytest.raises(DataSourceUnavailableError, match="MCP rate limited Desktop fallback: CDP is down"):
        asyncio.run(provider.get_chart_context("TVC:SILVER", "1h"))


def test_mtf_mcp_success_never_touches_the_desktop() -> None:
    desktop = StaticChart(error=AssertionError("desktop must not be used"))
    provider = FallbackChartProvider(StaticChart(result=_context(DataSource.OFFICIAL_MCP)), desktop)

    context = asyncio.run(provider.get_chart_context("TVC:SILVER", "1h"))

    assert context.source is DataSource.OFFICIAL_MCP
    assert context.warnings == []
