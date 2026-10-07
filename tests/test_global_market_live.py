"""Tests for the bounded, read-only official-MCP Global Market provider."""

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.desktop_bridge import DesktopWatchlistQuote, DesktopWatchlistQuoteSnapshot
from god_market_api.global_market import (
    GlobalMarketLiveSnapshotProvider,
    RECORDED_WATCHLIST_GROUPS,
    WatchlistGroupDefinition,
    WatchlistInstrumentDefinition,
)
from god_market_api.models import Candle, ChartContext, DataSource, MarketDirection, SourceState
from god_market_api.providers import DataSourceUnavailableError


NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def test_recorded_watchlist_matches_the_approved_ps_global_indices_snapshot() -> None:
    assert [(group.name, [item.symbol for item in group.instruments]) for group in RECORDED_WATCHLIST_GROUPS] == [
        (
            "USA",
            [
                "TVC:DJI",
                "DJCFD:DJT",
                "NASDAQ:NDX",
                "CBOE:MAGS",
                "NASDAQ:IXIC",
                "VANTAGE:USDINR",
                "TVC:SPX",
                "BLACKBULL:DJ30.F",
                "BLACKBULL:US30",
                "TVC:NYA",
                "CBOEFTSE:RUT",
                "TVC:DXY",
                "TVC:VIX",
            ],
        ),
        ("EUROPE", ["XETR:DAX", "TVC:CAC40", "FTSE:UKX"]),
        (
            "ASIA PACIFIC",
            [
                "NSEIX:NIFTY1!",
                "TVC:HSI",
                "TVC:NI225",
                "TVC:STI",
                "KRX:KOSPI",
                "ASX:XJO",
                "IDX:COMPOSITE",
                "SET:SET",
                "TWSE:TAIEX",
                "SSE:000300",
            ],
        ),
        ("INDIA ADRS", ["NYSE:INFY", "NYSE:WIT", "NYSE:IBN", "NYSE:HDB"]),
    ]
WATCHLIST = (
    WatchlistGroupDefinition(
        name="USA",
        instruments=(
            WatchlistInstrumentDefinition("TVC:SPX", "S&P 500"),
            WatchlistInstrumentDefinition("TVC:VIX", "CBOE Volatility Index"),
        ),
    ),
    WatchlistGroupDefinition(
        name="INDIA ADRS",
        instruments=(WatchlistInstrumentDefinition("NYSE:INFY", "Infosys ADR"),),
    ),
)


class FixtureProvider:
    def __init__(self, unavailable_symbols: set[str] | None = None) -> None:
        self.unavailable_symbols = unavailable_symbols or set()
        self.calls: list[tuple[str, str]] = []

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        self.calls.append((symbol, timeframe))
        if symbol in self.unavailable_symbols:
            raise DataSourceUnavailableError(f"{symbol} is unavailable")
        closes = {"TVC:SPX": (100.0, 105.0), "TVC:VIX": (20.0, 18.0)}.get(symbol, (10.0, 10.0))
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=NOW,
            freshness_state=SourceState.READY,
            candles=[
                Candle(timestamp=NOW - timedelta(days=1), open=closes[0], high=closes[0], low=closes[0], close=closes[0]),
                Candle(timestamp=NOW, open=closes[1], high=closes[1], low=closes[1], close=closes[1]),
            ],
        )


class FixtureDesktopWatchlistReader:
    def __init__(self, quotes: dict[str, DesktopWatchlistQuote]) -> None:
        self.quotes = quotes
        self.calls: list[list[str]] = []

    async def get_quotes(self, expected_symbols: list[str]) -> DesktopWatchlistQuoteSnapshot:
        self.calls.append(expected_symbols)
        return DesktopWatchlistQuoteSnapshot(quotes=self.quotes, observed_at=NOW)


def test_live_provider_uses_official_context_and_keeps_unavailable_items_visible() -> None:
    provider = FixtureProvider(unavailable_symbols={"NYSE:INFY"})
    live = GlobalMarketLiveSnapshotProvider(provider, watchlist_groups=WATCHLIST, clock=lambda: NOW)

    snapshot = asyncio.run(live.get_snapshot("daily"))

    assert snapshot.breadth.model_dump() == {"advancing": 1, "declining": 1, "unchanged": 0, "unavailable": 1}
    assert snapshot.groups[0].instruments[0].direction is MarketDirection.ADVANCING
    assert snapshot.groups[0].instruments[0].change_percent == 5.0
    assert snapshot.groups[0].instruments[0].source is DataSource.OFFICIAL_MCP
    unavailable = snapshot.groups[1].instruments[0]
    assert unavailable.direction is MarketDirection.UNAVAILABLE
    assert unavailable.source is DataSource.OFFICIAL_MCP
    assert unavailable.unavailable_reason == "NYSE:INFY is unavailable"
    assert provider.calls == [("TVC:SPX", "daily"), ("TVC:VIX", "daily"), ("NYSE:INFY", "daily")]


def test_live_provider_rejects_an_invalid_concurrency_limit() -> None:
    try:
        GlobalMarketLiveSnapshotProvider(FixtureProvider(), watchlist_groups=WATCHLIST, max_provider_concurrency=0)
    except ValueError as error:
        assert "at least 1" in str(error)
    else:
        raise AssertionError("Expected a validation error for a zero concurrency limit.")


def test_live_provider_reuses_a_recent_snapshot_without_extra_source_requests() -> None:
    provider = FixtureProvider()
    live = GlobalMarketLiveSnapshotProvider(provider, watchlist_groups=WATCHLIST, clock=lambda: NOW)

    first = asyncio.run(live.get_snapshot("daily"))
    second = asyncio.run(live.get_snapshot("daily"))

    assert first is second
    assert len(provider.calls) == 3


def test_live_provider_uses_desktop_watchlist_as_labeled_fallback_for_failed_official_item() -> None:
    provider = FixtureProvider(unavailable_symbols={"TVC:SPX"})
    desktop = FixtureDesktopWatchlistReader(
        {
            "TVC:SPX": DesktopWatchlistQuote(last_price=105.0, change_percent=0.5),
            "TVC:VIX": DesktopWatchlistQuote(last_price=18.0, change_percent=-1.0),
            "NYSE:INFY": DesktopWatchlistQuote(last_price=10.0, change_percent=None),
        }
    )
    live = GlobalMarketLiveSnapshotProvider(
        provider,
        desktop_watchlist_reader=desktop,
        watchlist_groups=WATCHLIST,
        clock=lambda: NOW,
    )

    snapshot = asyncio.run(live.get_snapshot("daily"))

    fallback = snapshot.groups[0].instruments[0]
    assert fallback.source is DataSource.DESKTOP_BRIDGE
    assert fallback.last_price == 105.0
    assert fallback.change_percent == 0.5
    assert fallback.direction is MarketDirection.ADVANCING
    assert any("Desktop-assisted fallback" in warning for warning in fallback.warnings)
    assert snapshot.breadth.model_dump() == {
        "advancing": 1,
        "declining": 1,
        "unchanged": 1,
        "unavailable": 0,
    }
    assert desktop.calls == [["TVC:SPX", "TVC:VIX", "NYSE:INFY"]]


def test_desktop_quote_without_daily_change_shows_price_but_stays_out_of_breadth() -> None:
    provider = FixtureProvider(unavailable_symbols={"TVC:SPX"})
    desktop = FixtureDesktopWatchlistReader(
        {"TVC:SPX": DesktopWatchlistQuote(last_price=105.0, change_percent=None)}
    )
    live = GlobalMarketLiveSnapshotProvider(
        provider,
        desktop_watchlist_reader=desktop,
        watchlist_groups=WATCHLIST,
        clock=lambda: NOW,
    )

    snapshot = asyncio.run(live.get_snapshot("daily"))

    fallback = snapshot.groups[0].instruments[0]
    assert fallback.source is DataSource.DESKTOP_BRIDGE
    assert fallback.last_price == 105.0
    assert fallback.change_percent is None
    assert fallback.direction is MarketDirection.UNAVAILABLE
    assert "no daily change percentage" in fallback.unavailable_reason
    assert snapshot.breadth.unavailable == 1


def test_default_global_market_endpoint_uses_the_live_official_provider() -> None:
    client = TestClient(create_app(provider=FixtureProvider()))

    response = client.get("/api/v1/global-market-sentiment", params={"timeframe": "daily"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["groups"][0]["instruments"][0]["source"] == "official_mcp"
    assert "Official TradingView MCP is the primary source" in payload["warnings"][0]
