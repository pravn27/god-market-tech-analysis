"""Tests for the bounded, read-only official-MCP Global Market provider."""

import asyncio
from contextlib import asynccontextmanager
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
from god_market_api.models import (
    Candle,
    ChartContext,
    DataSource,
    DesktopFallbackState,
    MarketDirection,
    SourceState,
)
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
    def __init__(
        self, unavailable_symbols: set[str] | None = None, transient_failures: dict[str, int] | None = None
    ) -> None:
        self.unavailable_symbols = unavailable_symbols or set()
        self.transient_failures = dict(transient_failures or {})
        self.calls: list[tuple[str, str]] = []

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        self.calls.append((symbol, timeframe))
        if symbol in self.unavailable_symbols:
            raise DataSourceUnavailableError(f"{symbol} is unavailable")
        if self.transient_failures.get(symbol, 0) > 0:
            self.transient_failures[symbol] -= 1
            raise DataSourceUnavailableError("The official MCP rejected the market-data request.")
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
    live = GlobalMarketLiveSnapshotProvider(
        provider, watchlist_groups=WATCHLIST, clock=lambda: NOW, retry_attempts=0
    )

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


def test_live_provider_retries_a_transient_official_failure_once() -> None:
    provider = FixtureProvider(transient_failures={"TVC:SPX": 1, "TVC:VIX": 2})
    live = GlobalMarketLiveSnapshotProvider(
        provider, watchlist_groups=WATCHLIST, clock=lambda: NOW, retry_delay_seconds=0
    )

    snapshot = asyncio.run(live.get_snapshot("daily"))

    spx, vix = snapshot.groups[0].instruments
    assert spx.source is DataSource.OFFICIAL_MCP
    assert spx.change_percent == 5.0
    assert vix.direction is MarketDirection.UNAVAILABLE
    assert vix.unavailable_reason == "The official MCP rejected the market-data request."
    assert provider.calls.count(("TVC:SPX", "daily")) == 2
    assert provider.calls.count(("TVC:VIX", "daily")) == 2


def test_live_provider_reads_every_item_inside_one_batch_session() -> None:
    class BatchingProvider(FixtureProvider):
        def __init__(self) -> None:
            super().__init__()
            self.in_batch = False
            self.calls_in_batch = 0
            self.batches = 0

        @asynccontextmanager
        async def batch_session(self):
            self.batches += 1
            self.in_batch = True
            try:
                yield
            finally:
                self.in_batch = False

        async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
            self.calls_in_batch += self.in_batch
            return await super().get_chart_context(symbol, timeframe)

    provider = BatchingProvider()
    live = GlobalMarketLiveSnapshotProvider(provider, watchlist_groups=WATCHLIST, clock=lambda: NOW)

    asyncio.run(live.get_snapshot("daily"))

    assert provider.batches == 1
    assert provider.calls_in_batch == 3


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
        retry_attempts=0,
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


DESKTOP_QUOTES = {
    "TVC:SPX": DesktopWatchlistQuote(last_price=105.0, change_percent=0.5),
    "TVC:VIX": DesktopWatchlistQuote(last_price=18.0, change_percent=-1.0),
    "NYSE:INFY": DesktopWatchlistQuote(last_price=10.0, change_percent=0.2),
}


class SessionProvider(FixtureProvider):
    """A provider whose shared official session opens or fails to open."""

    def __init__(self, *, session_opens: bool, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session_opens = session_opens

    @asynccontextmanager
    async def batch_session(self):
        yield self.session_opens


class FailingDesktopWatchlistReader(FixtureDesktopWatchlistReader):
    def __init__(self) -> None:
        super().__init__({})

    async def get_quotes(self, expected_symbols: list[str]) -> DesktopWatchlistQuoteSnapshot:
        self.calls.append(expected_symbols)
        raise DataSourceUnavailableError("The TradingView Desktop watchlist read failed.")


def test_snapshot_marks_partial_desktop_fallback() -> None:
    live = GlobalMarketLiveSnapshotProvider(
        FixtureProvider(unavailable_symbols={"TVC:SPX"}),
        desktop_watchlist_reader=FixtureDesktopWatchlistReader(DESKTOP_QUOTES),
        watchlist_groups=WATCHLIST,
        clock=lambda: NOW,
        retry_attempts=0,
    )

    assert asyncio.run(live.get_snapshot("daily")).desktop_fallback is DesktopFallbackState.PARTIAL


def test_slow_desktop_read_is_cancelled_when_official_data_is_complete() -> None:
    class SlowDesktopReader(FixtureDesktopWatchlistReader):
        cancelled = False

        async def get_quotes(self, expected_symbols: list[str]) -> DesktopWatchlistQuoteSnapshot:
            self.calls.append(expected_symbols)
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return await super().get_quotes(expected_symbols)

    desktop = SlowDesktopReader(DESKTOP_QUOTES)
    live = GlobalMarketLiveSnapshotProvider(
        FixtureProvider(), desktop_watchlist_reader=desktop, watchlist_groups=WATCHLIST, clock=lambda: NOW
    )

    snapshot = asyncio.run(asyncio.wait_for(live.get_snapshot("daily"), 2))

    assert len(desktop.calls) == 1
    assert desktop.cancelled
    assert snapshot.desktop_fallback is DesktopFallbackState.NONE
    assert all(item.source is DataSource.OFFICIAL_MCP for group in snapshot.groups for item in group.instruments)


def test_unopenable_official_session_goes_straight_to_desktop() -> None:
    provider = SessionProvider(session_opens=False)
    live = GlobalMarketLiveSnapshotProvider(
        provider,
        desktop_watchlist_reader=FixtureDesktopWatchlistReader(DESKTOP_QUOTES),
        watchlist_groups=WATCHLIST,
        clock=lambda: NOW,
    )

    snapshot = asyncio.run(live.get_snapshot("daily"))

    assert provider.calls == []
    assert snapshot.desktop_fallback is DesktopFallbackState.FULL
    assert snapshot.completeness.value == "complete"
    assert any("could not be opened" in warning for warning in snapshot.warnings)


def test_unopenable_official_session_still_tries_official_when_desktop_is_down() -> None:
    provider = SessionProvider(session_opens=False)
    live = GlobalMarketLiveSnapshotProvider(
        provider,
        desktop_watchlist_reader=FailingDesktopWatchlistReader(),
        watchlist_groups=WATCHLIST,
        clock=lambda: NOW,
    )

    snapshot = asyncio.run(live.get_snapshot("daily"))

    assert len(provider.calls) == 3
    assert snapshot.desktop_fallback is DesktopFallbackState.NONE
    assert snapshot.completeness.value == "complete"


def test_consecutive_official_failures_stop_further_official_requests() -> None:
    groups = (
        WatchlistGroupDefinition(
            name="USA",
            instruments=tuple(WatchlistInstrumentDefinition(f"TVC:X{index}", f"Index {index}") for index in range(6)),
        ),
    )
    provider = FixtureProvider(unavailable_symbols={f"TVC:X{index}" for index in range(6)})
    desktop = FixtureDesktopWatchlistReader(
        {f"TVC:X{index}": DesktopWatchlistQuote(last_price=1.0, change_percent=0.1) for index in range(6)}
    )
    live = GlobalMarketLiveSnapshotProvider(
        provider,
        desktop_watchlist_reader=desktop,
        watchlist_groups=groups,
        clock=lambda: NOW,
        max_provider_concurrency=1,
        retry_attempts=0,
    )

    snapshot = asyncio.run(live.get_snapshot("daily"))

    assert len(provider.calls) == 3
    assert all(item.source is DataSource.DESKTOP_BRIDGE for item in snapshot.groups[0].instruments)
    assert any("3 consecutive official" in warning for warning in snapshot.warnings)


def test_official_time_budget_hands_slow_items_to_desktop() -> None:
    class SlowProvider(FixtureProvider):
        async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
            if symbol == "TVC:VIX":
                await asyncio.sleep(5)
            return await super().get_chart_context(symbol, timeframe)

    live = GlobalMarketLiveSnapshotProvider(
        SlowProvider(),
        desktop_watchlist_reader=FixtureDesktopWatchlistReader(DESKTOP_QUOTES),
        watchlist_groups=WATCHLIST,
        clock=lambda: NOW,
        official_time_budget_seconds=0.2,
    )

    snapshot = asyncio.run(live.get_snapshot("daily"))

    spx, vix = snapshot.groups[0].instruments
    assert spx.source is DataSource.OFFICIAL_MCP
    assert vix.source is DataSource.DESKTOP_BRIDGE
    assert any("0.2 s refresh budget" in warning for warning in vix.warnings)


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
        retry_attempts=0,
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
