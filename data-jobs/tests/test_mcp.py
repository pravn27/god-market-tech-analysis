import asyncio
from datetime import datetime, timezone

import pytest

from data_jobs.fallback import QuotaExhaustedError
from data_jobs.mcp import MCP_SOURCE, OfficialMcpDailyFetcher
from god_market_api.models import Candle, ChartContext, DataSource, SourceState
from god_market_api.providers import DataSourceUnavailableError, OfficialQuotaExceededError

UTC = timezone.utc
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


class FakeOfficialProvider:
    def __init__(self, *, error=None, candles=None):
        self.error = error
        self.candles = candles or [
            Candle(timestamp=datetime(2026, 10, 20, tzinfo=UTC), open=1, high=3, low=0.5, close=2, volume=9),
            Candle(timestamp=datetime(2026, 10, 21, tzinfo=UTC), open=2, high=4, low=1.5, close=3, volume=8),
            Candle(timestamp=datetime(2026, 10, 22, tzinfo=UTC), open=3, high=5, low=2.5, close=4, volume=7),
        ]
        self.requests = []

    async def get_price_context(self, symbol, timeframe, *, candle_count=2):
        self.requests.append((symbol, timeframe, candle_count))
        if self.error is not None:
            raise self.error
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=self.candles[-1].timestamp,
            freshness_state=SourceState.READY,
            candles=self.candles,
        )


def _fetcher(provider):
    return OfficialMcpDailyFetcher(provider, loop=asyncio.new_event_loop(), clock=lambda: NOW)


def test_daily_candles_come_back_as_bars_from_the_official_source():
    provider = FakeOfficialProvider()

    result = _fetcher(provider).fetch("BLACKBULL:DJ30.F", "1D", count=3)

    assert result.source == MCP_SOURCE
    assert provider.requests == [("BLACKBULL:DJ30.F", "1D", 3)]
    assert [bar.close for bar in result.bars] == [2, 3, 4]
    assert [bar.is_closed for bar in result.bars] == [True, True, False]


def test_a_quota_block_is_passed_on_as_the_fallback_signal():
    provider = FakeOfficialProvider(error=OfficialQuotaExceededError("TradingView MCP daily quota is used up."))

    with pytest.raises(QuotaExhaustedError, match="quota is used up"):
        _fetcher(provider).fetch("DJI", "1D", count=3)


def test_other_mcp_failures_stay_ordinary_failures():
    provider = FakeOfficialProvider(error=DataSourceUnavailableError("MCP session expired."))

    with pytest.raises(DataSourceUnavailableError) as raised:
        _fetcher(provider).fetch("DJI", "1D", count=3)
    assert not isinstance(raised.value, QuotaExhaustedError)


def test_only_daily_bars_are_requested_from_the_mcp():
    provider = FakeOfficialProvider()

    with pytest.raises(ValueError, match="reads daily bars"):
        _fetcher(provider).fetch("DJI", "1W", count=3)
    assert provider.requests == []
