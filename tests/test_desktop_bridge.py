import asyncio
from datetime import datetime, timezone

import pytest

from god_market_api.desktop_bridge import TradingViewDesktopWatchlistReader, parse_watchlist_payload
from god_market_api.models import DataSource, SourceState
from god_market_api.providers import DataSourceUnavailableError


def test_desktop_watchlist_parser_normalizes_prices_and_change_percent():
    observed_at = datetime(2026, 10, 7, 8, tzinfo=timezone.utc)
    payload = {
        "success": True,
        "symbols": [
            {"symbol": "TVC:SPX", "last": "7,818.93", "change_percent": "0.58%"},
            {"symbol": "TVC:VIX", "last": "15.27", "change_percent": None},
        ],
    }

    result = parse_watchlist_payload(payload, ["TVC:SPX", "TVC:VIX"], observed_at=observed_at)

    assert result.observed_at == observed_at
    assert result.quotes["TVC:SPX"].last_price == 7818.93
    assert result.quotes["TVC:SPX"].change_percent == 0.58
    assert result.quotes["TVC:VIX"].last_price == 15.27
    assert result.quotes["TVC:VIX"].change_percent is None


def test_desktop_watchlist_parser_accepts_unicode_minus_for_declines():
    payload = {
        "success": True,
        "symbols": [
            {"symbol": "TVC:DJI", "last": "51,091.10", "change_percent": "\u22120.32%"},
            {"symbol": "TVC:HSI", "last": "23,785.80", "change_percent": "-1.05%"},
        ],
    }

    result = parse_watchlist_payload(payload, ["TVC:DJI", "TVC:HSI"])

    assert result.quotes["TVC:DJI"].change_percent == -0.32
    assert result.quotes["TVC:HSI"].change_percent == -1.05


def test_desktop_watchlist_parser_rejects_a_different_selected_symbol_universe():
    payload = {"success": True, "symbols": [{"symbol": "TVC:SPX", "last": "1", "change_percent": "0%"}]}

    with pytest.raises(DataSourceUnavailableError, match="not PS_Global_Indices"):
        parse_watchlist_payload(payload, ["TVC:VIX"])


def test_desktop_watchlist_parser_uses_visible_approved_rows_in_any_order():
    payload = {
        "success": True,
        "symbols": [
            {"symbol": "TVC:VIX", "last": "15.27", "change_percent": "1.19%"},
            {"symbol": "TVC:SPX", "last": "7,818.93", "change_percent": "-0.20%"},
        ],
    }

    result = parse_watchlist_payload(payload, ["TVC:SPX", "TVC:VIX", "NYSE:INFY", "NYSE:HDB"])

    assert set(result.quotes) == {"TVC:SPX", "TVC:VIX"}
    assert result.quotes["TVC:SPX"].change_percent == -0.2


def test_desktop_watchlist_parser_ignores_a_minority_of_foreign_rows():
    payload = {
        "success": True,
        "symbols": [
            {"symbol": "TVC:SPX", "last": "1", "change_percent": "0.1%"},
            {"symbol": "TVC:VIX", "last": "2", "change_percent": "0.2%"},
            {"symbol": "NSE:RELIANCE", "last": "3", "change_percent": "0.3%"},
        ],
    }

    result = parse_watchlist_payload(payload, ["TVC:SPX", "TVC:VIX"])

    assert set(result.quotes) == {"TVC:SPX", "TVC:VIX"}


def test_desktop_watchlist_parser_rejects_another_list_with_a_little_overlap():
    payload = {
        "success": True,
        "symbols": [
            {"symbol": "NSEIX:NIFTY1!", "last": "1", "change_percent": "0.1%"},
            {"symbol": "NSE:RELIANCE", "last": "2", "change_percent": "0.2%"},
            {"symbol": "NSE:TCS", "last": "3", "change_percent": "0.3%"},
        ],
    }

    with pytest.raises(DataSourceUnavailableError, match="not PS_Global_Indices"):
        parse_watchlist_payload(payload, ["NSEIX:NIFTY1!", "TVC:SPX"])


def test_desktop_reader_health_reports_configuration_and_last_failure(tmp_path):
    unconfigured = asyncio.run(TradingViewDesktopWatchlistReader(None).health())
    assert unconfigured.state is SourceState.NOT_CONFIGURED

    reader = TradingViewDesktopWatchlistReader(tmp_path / "missing-cli.js")
    with pytest.raises(DataSourceUnavailableError):
        asyncio.run(reader.get_quotes(["TVC:SPX"]))
    failed = asyncio.run(reader.health())
    assert failed.source is DataSource.DESKTOP_BRIDGE
    assert failed.state is SourceState.UNAVAILABLE
    assert "not found" in failed.detail
