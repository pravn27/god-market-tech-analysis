from datetime import timedelta

import pytest
from god_market_api.global_market import RECORDED_WATCHLIST_GROUPS

from data_jobs import registry
from data_jobs.registry import (
    DERIVED_PERIODS,
    GLOBAL_MARKET_DAILY,
    InstrumentListUnavailable,
    global_market_symbols,
    registered_jobs,
)


class FakeWatchlistReader:
    """Stands in for the Desktop bridge: answers ``watchlist get`` with a fixed payload."""

    def __init__(self, payload):
        self.payload = payload

    async def watchlist_payload(self):
        return self.payload


def _sequence_of(groups):
    sequence = []
    for group in groups:
        sequence.append({"section": group.name})
        sequence.extend({"symbol": instrument.symbol} for instrument in group.instruments)
    return sequence


RECORDED_SYMBOLS = [instrument.symbol for group in RECORDED_WATCHLIST_GROUPS for instrument in group.instruments]


def _reader(payload):
    return lambda: FakeWatchlistReader(payload)


def test_the_instrument_list_is_every_symbol_of_ps_global_indices_in_on_screen_order():
    payload = {"success": True, "sequence": _sequence_of(RECORDED_WATCHLIST_GROUPS)}

    assert global_market_symbols(_reader(payload)) == tuple(RECORDED_SYMBOLS)


def test_a_symbol_listed_twice_is_read_once():
    sequence = _sequence_of(RECORDED_WATCHLIST_GROUPS) + [{"symbol": RECORDED_SYMBOLS[0]}]
    payload = {"success": True, "sequence": sequence}

    assert global_market_symbols(_reader(payload)) == tuple(RECORDED_SYMBOLS)


def test_a_closed_desktop_is_reported_as_an_unavailable_instrument_list():
    with pytest.raises(InstrumentListUnavailable, match="did not return a usable watchlist"):
        global_market_symbols(_reader({"success": False}))


def test_a_different_visible_watchlist_is_refused_rather_than_fetched():
    payload = {
        "success": True,
        "sequence": [{"symbol": "NASDAQ:AAPL"}, {"symbol": "NASDAQ:MSFT"}, {"symbol": "NYSE:KO"}],
    }

    with pytest.raises(InstrumentListUnavailable, match="not PS_Global_Indices"):
        global_market_symbols(_reader(payload))


def test_registered_jobs_is_the_daily_global_market_job_with_derived_periods(monkeypatch):
    monkeypatch.setattr(registry, "global_market_symbols", lambda: ("TVC:SPX", "TVC:DJI"))

    (spec,) = registered_jobs()

    assert spec.name == GLOBAL_MARKET_DAILY
    assert spec.interval == timedelta(days=1)
    assert spec.symbols == ("TVC:SPX", "TVC:DJI")
    assert spec.timeframes == ("1D",)
    assert spec.derived_periods == DERIVED_PERIODS == ("1W", "1M", "3M")
    assert spec.bar_count >= 120  # enough history for the quarterly bars to complete
