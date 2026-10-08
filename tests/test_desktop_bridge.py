from datetime import datetime, timezone

import pytest

from god_market_api.desktop_bridge import parse_watchlist_payload
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

    with pytest.raises(DataSourceUnavailableError, match="does not match"):
        parse_watchlist_payload(payload, ["TVC:VIX"])
