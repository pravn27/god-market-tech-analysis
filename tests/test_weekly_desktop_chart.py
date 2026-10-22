"""Weekly values: the open TradingView Desktop chart prices the items the official MCP cannot."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.desktop_bridge import DesktopWatchlistQuoteSnapshot
from god_market_api.global_market import (
    DESKTOP_CHART_FAILURE_LIMIT,
    RECORDED_WATCHLIST_GROUPS,
    GlobalMarketLiveSnapshotProvider,
    WatchlistGroupDefinition,
    WatchlistInstrumentDefinition,
)
from god_market_api.models import Candle, ChartContext, DataSource, MarketDirection, SourceState
from god_market_api.oauth import OfficialMCPOAuthCoordinator
from god_market_api.providers import DataSourceUnavailableError

NOW = datetime(2026, 10, 22, 6, 0, tzinfo=timezone.utc)
QUOTA_TEXT = "TOOL_QUOTA_EXCEEDED - Tool call quota exceeded (resets at 00:00 UTC.)"
WATCHLIST = (
    WatchlistGroupDefinition(
        "USA",
        (
            WatchlistInstrumentDefinition("TVC:SPX", "S&P 500"),
            WatchlistInstrumentDefinition("TVC:VIX", "VIX"),
        ),
    ),
)


class OfficialDown:
    """Official MCP stand-in that fails every read."""

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        raise DataSourceUnavailableError("The official MCP rejected the market-data request.")


class OfficialPricesOnly:
    """Official MCP stand-in that prices every symbol except the ones listed as unavailable."""

    def __init__(self, unavailable: set[str]) -> None:
        self.unavailable = unavailable

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        if symbol in self.unavailable:
            raise DataSourceUnavailableError(f"{symbol} is unavailable")
        return _context(symbol, timeframe, previous=100.0, current=101.0, source=DataSource.OFFICIAL_MCP)


class FakeChart:
    """Open-chart stand-in: records each read and returns two weekly bars, or fails for chosen symbols."""

    def __init__(self, *, fail: set[str] | None = None, previous: float = 100.0, current: float = 103.0) -> None:
        self.fail = fail or set()
        self.previous = previous
        self.current = current
        self.calls: list[tuple[str, str]] = []

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        self.calls.append((symbol, timeframe))
        if symbol in self.fail:
            raise DataSourceUnavailableError("TradingView Desktop did not load the chart in time.")
        return _context(symbol, timeframe, previous=self.previous, current=self.current, source=DataSource.DESKTOP_BRIDGE)


def _context(symbol: str, timeframe: str, *, previous: float, current: float, source: DataSource) -> ChartContext:
    return ChartContext(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        source_timestamp=NOW,
        freshness_state=SourceState.READY,
        candles=[
            Candle(timestamp=NOW - timedelta(weeks=1), open=previous, high=previous, low=previous, close=previous),
            Candle(timestamp=NOW, open=current, high=current, low=current, close=current),
        ],
    )


def _provider(official, chart, **kwargs) -> GlobalMarketLiveSnapshotProvider:
    return GlobalMarketLiveSnapshotProvider(
        official,
        watchlist_groups=WATCHLIST,
        clock=lambda: NOW,
        retry_attempts=0,
        desktop_chart_provider=chart,
        **kwargs,
    )


def test_weekly_items_the_official_mcp_misses_are_priced_from_the_open_chart() -> None:
    chart = FakeChart(current=103.0, previous=100.0)
    snapshot = asyncio.run(_provider(OfficialDown(), chart).get_snapshot("1W"))

    spx, vix = snapshot.groups[0].instruments
    for item in (spx, vix):
        assert item.source is DataSource.DESKTOP_BRIDGE
        assert item.direction is MarketDirection.ADVANCING
        assert item.last_price == 103.0
        assert round(item.change_percent, 6) == 3.0
    assert snapshot.desktop_fallback == "full"
    assert snapshot.breadth.advancing == 2
    assert any("read from the open TradingView Desktop chart" in warning for warning in snapshot.warnings)
    assert chart.calls == [("TVC:SPX", "1W"), ("TVC:VIX", "1W")]


def test_official_prices_are_kept_and_the_chart_is_only_asked_for_the_gaps() -> None:
    chart = FakeChart()
    snapshot = asyncio.run(_provider(OfficialPricesOnly({"TVC:VIX"}), chart).get_snapshot("1W"))

    spx, vix = snapshot.groups[0].instruments
    assert spx.source is DataSource.OFFICIAL_MCP
    assert vix.source is DataSource.DESKTOP_BRIDGE
    assert chart.calls == [("TVC:VIX", "1W")]


def test_chart_reads_stop_after_consecutive_failures_and_say_why() -> None:
    chart = FakeChart(fail={"TVC:SPX", "TVC:VIX"} | {f"X:{i}" for i in range(5)})
    many = (
        WatchlistGroupDefinition(
            "USA",
            tuple(WatchlistInstrumentDefinition(f"X:{i}", f"Index {i}") for i in range(5))
            + (WatchlistInstrumentDefinition("TVC:SPX", "S&P 500"),),
        ),
    )
    provider = GlobalMarketLiveSnapshotProvider(
        OfficialDown(),
        watchlist_groups=many,
        clock=lambda: NOW,
        retry_attempts=0,
        desktop_chart_provider=chart,
    )

    snapshot = asyncio.run(provider.get_snapshot("1W"))

    assert len(chart.calls) == DESKTOP_CHART_FAILURE_LIMIT
    assert all(item.direction is MarketDirection.UNAVAILABLE for group in snapshot.groups for item in group.instruments)
    assert any(f"stopped after {DESKTOP_CHART_FAILURE_LIMIT} consecutive failures" in w for w in snapshot.warnings)


def test_daily_never_reads_the_chart() -> None:
    chart = FakeChart()
    snapshot = asyncio.run(_provider(OfficialDown(), chart).get_snapshot("1D"))

    assert chart.calls == []
    assert all(item.source is DataSource.OFFICIAL_MCP for group in snapshot.groups for item in group.instruments)


def test_chart_reads_are_reused_for_thirty_minutes_across_refreshes() -> None:
    chart = FakeChart()
    provider = _provider(OfficialDown(), chart)

    asyncio.run(provider.get_snapshot("1W"))
    asyncio.run(provider.get_snapshot("1W", force_refresh=True))

    assert len(chart.calls) == 2  # one read per symbol, then the cache served the forced refresh


class _NoStorage:
    async def get_tokens(self):
        return None


class _DesktopWatchlist:
    async def watchlist_payload(self):
        sequence = []
        for group in RECORDED_WATCHLIST_GROUPS:
            sequence.append({"section": group.name})
            sequence.extend({"symbol": item.symbol} for item in group.instruments)
        return {"success": True, "sequence": sequence}

    async def get_quotes(self, expected_symbols):
        return DesktopWatchlistQuoteSnapshot(quotes={}, observed_at=NOW)


def test_weekly_endpoint_leaves_the_chart_alone_unless_the_desktop_weekly_flag_is_on(monkeypatch) -> None:
    monkeypatch.delenv("GLOBAL_MARKET_DESKTOP_WEEKLY", raising=False)
    coordinator = OfficialMCPOAuthCoordinator(storage=_NoStorage(), clock=lambda: NOW)

    async def quota_blocked(name, arguments):
        return SimpleNamespace(isError=True, content=[SimpleNamespace(text=QUOTA_TEXT)])

    monkeypatch.setattr(coordinator, "_call_tool_authorized", quota_blocked)
    chart = FakeChart()
    client = TestClient(
        create_app(oauth=coordinator, desktop_watchlist_reader=_DesktopWatchlist(), desktop_candles=chart)
    )

    payload = client.get("/api/v1/global-market-sentiment", params={"timeframe": "1W"}).json()

    assert chart.calls == []
    total = sum(len(group.instruments) for group in RECORDED_WATCHLIST_GROUPS)
    assert payload["breadth"]["unavailable"] == total
    assert all(item["source"] == "official_mcp" for group in payload["groups"] for item in group["instruments"])


def test_weekly_endpoint_uses_the_chart_when_the_official_quota_is_used_up(monkeypatch) -> None:
    monkeypatch.setenv("GLOBAL_MARKET_DESKTOP_WEEKLY", "true")
    coordinator = OfficialMCPOAuthCoordinator(storage=_NoStorage(), clock=lambda: NOW)
    official_calls: list[str] = []

    async def quota_blocked(name, arguments):
        official_calls.append(name)
        return SimpleNamespace(isError=True, content=[SimpleNamespace(text=QUOTA_TEXT)])

    monkeypatch.setattr(coordinator, "_call_tool_authorized", quota_blocked)
    chart = FakeChart()
    client = TestClient(
        create_app(oauth=coordinator, desktop_watchlist_reader=_DesktopWatchlist(), desktop_candles=chart)
    )

    response = client.get("/api/v1/global-market-sentiment", params={"timeframe": "1W"})

    assert response.status_code == 200
    payload = response.json()
    instruments = [item for group in payload["groups"] for item in group["instruments"]]
    assert len(instruments) == sum(len(group.instruments) for group in RECORDED_WATCHLIST_GROUPS)
    assert all(item["source"] == "desktop_bridge" for item in instruments)
    assert all(item["change_percent"] is not None for item in instruments)
    assert payload["desktop_fallback"] == "full"
    assert len(official_calls) == 1  # the quota block stopped every later official call
    assert len(chart.calls) == len(instruments)
