import asyncio
from datetime import datetime, timezone

import pytest

from god_market_api.models import SourceState
from god_market_api.providers import (
    DataSourceUnavailableError,
    OfficialMCPProvider,
    normalize_timeframe,
    technicals_interval,
)


class FakeToolCaller:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        response = self.responses[name]
        if isinstance(response, Exception):
            raise response
        return response


def test_provider_normalizes_official_mcp_ohlcv_and_technical_snapshot():
    caller = FakeToolCaller(
        {
            "mcp-tv-get-ohlcv": {
                "bars": [
                    {"t": 1735689600, "o": 100, "h": 106, "l": 99, "c": 104, "v": 1200},
                    {"t": 1735776000, "o": 104, "h": 109, "l": 103, "c": 108, "v": 1300},
                ]
            },
            "mcp-tv-get-technicals-rating": {
                "summary": {"RECOMMENDATION": "BUY"},
                "moving_averages": "STRONG_BUY",
                "oscillators": "NEUTRAL",
                "values": {"RSI": 57.4, "MACD": 1.3, "ignored": "not-numeric"},
            },
        }
    )
    provider = OfficialMCPProvider(tool_caller=caller, candle_count=250)

    context = asyncio.run(provider.get_chart_context("NSE:NIFTY", "daily"))

    assert context.timeframe == "1D"
    assert context.source_timestamp == datetime.fromtimestamp(1735776000, tz=timezone.utc)
    assert context.candles[-1].close == 108
    assert context.technicals.recommendation == "BUY"
    assert context.technicals.moving_averages == "STRONG_BUY"
    assert context.technicals.values == {"RSI": 57.4, "MACD": 1.3}
    assert caller.calls == [
        ("mcp-tv-get-ohlcv", {"symbol": "NSE:NIFTY", "interval": "1D", "count": 250}),
        ("mcp-tv-get-technicals-rating", {"symbol": "NSE:NIFTY", "interval": "1D"}),
    ]
    health = asyncio.run(provider.health())
    assert health.state == SourceState.READY
    assert health.last_success_at is not None


def test_provider_rejects_invalid_or_empty_mcp_candle_response():
    provider = OfficialMCPProvider(
        tool_caller=FakeToolCaller(
            {"mcp-tv-get-ohlcv": {"bars": []}, "mcp-tv-get-technicals-rating": {"summary": "BUY"}}
        )
    )

    with pytest.raises(DataSourceUnavailableError, match="no OHLCV candles"):
        asyncio.run(provider.get_chart_context("NSE:NIFTY", "1h"))


def test_provider_keeps_current_ohlcv_when_the_technical_snapshot_is_unavailable():
    provider = OfficialMCPProvider(
        tool_caller=FakeToolCaller(
            {
                "mcp-tv-get-ohlcv": {"bars": [{"t": 1735689600, "o": 100, "h": 106, "l": 99, "c": 104}]},
                "mcp-tv-get-technicals-rating": {"success": False, "error": "rate limited"},
            }
        )
    )

    context = asyncio.run(provider.get_chart_context("NSE:NIFTY", "1h"))

    assert context.candles[0].close == 104
    assert context.technicals is None
    assert context.warnings == [
        "The official technical snapshot is temporarily unavailable; OHLCV context is still current."
    ]


def test_provider_can_fetch_a_small_ohlcv_only_context_for_market_breadth():
    caller = FakeToolCaller(
        {
            "mcp-tv-get-ohlcv": {
                "bars": [
                    {"t": 1735689600, "o": 100, "h": 106, "l": 99, "c": 104},
                    {"t": 1735776000, "o": 104, "h": 109, "l": 103, "c": 108},
                ]
            }
        }
    )
    provider = OfficialMCPProvider(tool_caller=caller, candle_count=500)

    context = asyncio.run(provider.get_price_context("NSE:NIFTY", "daily", candle_count=2))

    assert context.technicals is None
    assert len(context.candles) == 2
    assert caller.calls == [("mcp-tv-get-ohlcv", {"symbol": "NSE:NIFTY", "interval": "1D", "count": 2})]


def test_provider_accepts_valid_ohlc_when_index_volume_is_null():
    provider = OfficialMCPProvider(
        tool_caller=FakeToolCaller(
            {
                "mcp-tv-get-ohlcv": {
                    "bars": [
                        {"t": 1791207000, "o": 100, "h": 103, "l": 99, "c": 101, "v": None},
                        {"t": 1791293400, "o": 101, "h": 106, "l": 100, "c": 105, "v": None},
                    ]
                }
            }
        )
    )

    context = asyncio.run(provider.get_price_context("TVC:DJI", "daily", candle_count=2))

    assert [candle.close for candle in context.candles] == [101, 105]
    assert [candle.volume for candle in context.candles] == [None, None]


@pytest.mark.parametrize(
    ("input_timeframe", "expected"),
    [("daily", "1D"), ("1d", "1D"), ("weekly", "1W"), ("monthly", "M"), ("4h", "4h")],
)
def test_normalize_timeframe_accepts_dashboard_labels(input_timeframe, expected):
    assert normalize_timeframe(input_timeframe) == expected


def test_normalize_timeframe_rejects_unknown_interval():
    with pytest.raises(DataSourceUnavailableError, match="Unsupported timeframe"):
        normalize_timeframe("2h")


def test_monthly_ohlcv_interval_is_mapped_for_the_technicals_tool():
    assert technicals_interval("M") == "1M"
    assert technicals_interval("1D") == "1D"
