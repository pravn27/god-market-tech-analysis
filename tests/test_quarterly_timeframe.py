"""Tests for the three-month (quarterly) timeframe built from the official MCP's daily bars."""

import asyncio
from datetime import datetime, timezone

import pytest

from god_market_api.models import Candle
from god_market_api.providers import (
    DataSourceUnavailableError,
    OfficialMCPProvider,
    normalize_timeframe,
    quarterly_candles,
)


def _month(year: int, month: int, open_: float, high: float, low: float, close: float, volume: float = 10.0) -> Candle:
    return Candle(
        timestamp=datetime(year, month, 1, tzinfo=timezone.utc),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
    )


class FakeToolCaller:
    def __init__(self, bars):
        self.bars = bars
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return {"bars": self.bars}


def test_three_month_aliases_normalize_to_the_quarterly_interval():
    for alias in ("3M", "3 month", "3month", "quarterly", "3mo"):
        assert normalize_timeframe(alias) == "3M"


def test_bars_group_into_calendar_quarters_with_full_ohlc_rules() -> None:
    monthly = [
        _month(2026, 1, 100, 110, 95, 105, 1),
        _month(2026, 2, 105, 130, 100, 120, 2),
        _month(2026, 3, 120, 125, 90, 95, 3),
        _month(2026, 4, 95, 100, 94, 99, 4),
    ]

    quarters = quarterly_candles(monthly)

    assert [q.timestamp.month for q in quarters] == [1, 4]
    q1 = quarters[0]
    assert (q1.open, q1.high, q1.low, q1.close, q1.volume) == (100, 130, 90, 95, 6)
    assert quarters[1].close == 99  # the open quarter is partial and still reported


def test_three_month_context_requests_daily_bars_and_returns_the_latest_quarters() -> None:
    bars = [
        {"t": 1738368000 + index * 86_400, "o": 100 + index, "h": 101 + index, "l": 99 + index, "c": 100 + index}
        for index in range(200)
    ]
    caller = FakeToolCaller(bars)
    provider = OfficialMCPProvider(tool_caller=caller)

    context = asyncio.run(provider.get_price_context("NSE:NIFTY", "3M", candle_count=2))

    assert caller.calls == [("mcp-tv-get-ohlcv", {"symbol": "NSE:NIFTY", "interval": "1D", "count": 320})]
    assert context.timeframe == "3M"
    assert len(context.candles) == 2
    assert context.candles[-1].timestamp <= datetime.now(timezone.utc)


def test_three_month_context_without_daily_bars_is_unavailable() -> None:
    provider = OfficialMCPProvider(tool_caller=FakeToolCaller([]))

    with pytest.raises(DataSourceUnavailableError):
        asyncio.run(provider.get_price_context("NSE:NIFTY", "3M", candle_count=2))


def test_global_market_endpoint_rejects_an_unsupported_timeframe() -> None:
    from fastapi.testclient import TestClient

    from god_market_api.app import create_app

    class NoPrices:
        async def get_chart_context(self, symbol, timeframe):
            raise DataSourceUnavailableError("unused")

    client = TestClient(create_app(provider=NoPrices()))

    response = client.get("/api/v1/global-market-sentiment", params={"timeframe": "2h"})

    assert response.status_code == 422


def test_desktop_watchlist_quotes_are_never_used_for_non_daily_timeframes() -> None:
    from god_market_api.global_market import GlobalMarketLiveSnapshotProvider, RECORDED_WATCHLIST_GROUPS

    class RecordingDesktop:
        def __init__(self):
            self.calls = 0

        async def get_quotes(self, expected_symbols):
            self.calls += 1
            raise DataSourceUnavailableError("Desktop must not be asked for weekly quotes.")

    class NoPrices:
        async def get_chart_context(self, symbol, timeframe):
            raise DataSourceUnavailableError("MCP unavailable")

    desktop = RecordingDesktop()
    live = GlobalMarketLiveSnapshotProvider(
        NoPrices(),
        desktop_watchlist_reader=desktop,
        watchlist_groups=RECORDED_WATCHLIST_GROUPS[:1],
        retry_attempts=0,
    )

    snapshot = asyncio.run(live.get_snapshot("1W"))

    assert desktop.calls == 0
    assert any("supplies daily quotes only" in warning for warning in snapshot.warnings)
