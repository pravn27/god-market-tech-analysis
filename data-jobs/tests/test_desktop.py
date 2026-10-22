import asyncio
from datetime import datetime, timezone

from data_jobs.desktop import DesktopChartDailyReader
from god_market_api.models import Candle, ChartContext, DataSource, SourceState
from god_market_api.providers import DataSourceUnavailableError

UTC = timezone.utc
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


class FakeCli:
    def __init__(self, status=None, error=None):
        self.status = status
        self.error = error

    async def run(self, *args):
        if self.error is not None:
            raise self.error
        return self.status


class FakeChartProvider:
    def __init__(self, candles):
        self.candles = candles
        self.requests = []

    async def get_chart_context(self, symbol, timeframe):
        self.requests.append((symbol, timeframe))
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.DESKTOP_BRIDGE,
            source_timestamp=self.candles[-1].timestamp,
            freshness_state=SourceState.READY,
            candles=self.candles,
        )


def _candle(day, close):
    return Candle(
        timestamp=datetime(2026, 10, day, tzinfo=UTC),
        open=close - 1,
        high=close + 1,
        low=close - 2,
        close=close,
        volume=1000.0,
    )


def _reader(provider=None, cli=None):
    return DesktopChartDailyReader(
        provider=provider or FakeChartProvider([_candle(21, 100.0)]),
        cli=cli or FakeCli(),
        loop=asyncio.new_event_loop(),
    )


def test_open_and_responding_desktop_is_detected():
    healthy = {"success": True, "cdp_connected": True, "api_available": True}

    assert _reader(cli=FakeCli(status=healthy)).is_open() is True


def test_a_desktop_without_a_connected_debugger_is_not_open():
    not_connected = {"success": True, "cdp_connected": False, "api_available": True}

    assert _reader(cli=FakeCli(status=not_connected)).is_open() is False


def test_a_missing_bridge_means_the_desktop_is_not_open():
    reader = _reader(cli=FakeCli(error=DataSourceUnavailableError("bridge not configured")))

    assert reader.is_open() is False


def test_daily_candles_become_bars_and_the_forming_day_is_marked_open():
    provider = FakeChartProvider([_candle(20, 99.0), _candle(21, 100.0), _candle(22, 101.0)])
    reader = _reader(provider=provider)

    bars = reader.read_daily("NSEIX:NIFTY1!", count=3, now=NOW)

    assert provider.requests == [("NSEIX:NIFTY1!", "1D")]
    assert [bar.close for bar in bars] == [99.0, 100.0, 101.0]
    assert [bar.is_closed for bar in bars] == [True, True, False]


def test_only_the_most_recent_bars_are_kept_when_more_are_read():
    provider = FakeChartProvider([_candle(19, 98.0), _candle(20, 99.0), _candle(21, 100.0)])

    bars = _reader(provider=provider).read_daily("DJ30", count=2, now=NOW)

    assert [bar.close for bar in bars] == [99.0, 100.0]
