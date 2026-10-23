"""The MTF instrument list reads the visible Desktop watchlist only while the official quota is used up."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from god_market_api.global_market import RECORDED_WATCHLIST_GROUPS, WatchlistUnavailableError
from god_market_api.models import MtfInstrumentCatalog
from god_market_api.mtf_analysis import (
    CATALOG_ORIGIN_DESKTOP,
    CATALOG_ORIGIN_SNAPSHOT,
    DesktopMtfCatalogSource,
    MultiTimeframeAnalysisService,
    UnknownInstrumentError,
    load_instrument_catalog,
)
from god_market_api.providers import DataSourceUnavailableError
from god_market_api.watchlist_source import DesktopWatchlistSectionSource

START = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now


class FakeDesktopReader:
    """Stands in for the Desktop bridge: returns a ``watchlist get`` style payload, or raises."""

    def __init__(self, sequence=None, error: Exception | None = None) -> None:
        self.sequence = sequence
        self.error = error
        self.calls = 0

    async def watchlist_payload(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return {"success": True, "sequence": self.sequence, "symbols": []}


def _snapshot_sequence(catalog: MtfInstrumentCatalog) -> list[dict]:
    """The bridge sends rows without section headers when the visible list has none."""
    return [{"symbol": instrument.symbol} for section in catalog.sections for instrument in section.instruments]


def _visible_symbols(catalog: MtfInstrumentCatalog) -> set[str]:
    return {instrument.symbol for section in catalog.sections for instrument in section.instruments}


def _source(reader, *, quota_blocked: bool, clock: Clock | None = None) -> DesktopMtfCatalogSource:
    snapshot = load_instrument_catalog()
    return DesktopMtfCatalogSource(
        reader,
        snapshot,
        quota_blocked=lambda: quota_blocked,
        clock=clock or Clock(),
    )


def test_quota_available_uses_the_snapshot_and_never_reads_the_desktop() -> None:
    reader = FakeDesktopReader(sequence=[])

    catalog = asyncio.run(_source(reader, quota_blocked=False).catalog())

    assert reader.calls == 0
    assert catalog.origin == CATALOG_ORIGIN_SNAPSHOT
    assert catalog == load_instrument_catalog()


def test_quota_used_up_reads_the_visible_watchlist_and_keeps_the_snapshot_sections() -> None:
    snapshot = load_instrument_catalog()
    reader = FakeDesktopReader(sequence=_snapshot_sequence(snapshot))

    catalog = asyncio.run(_source(reader, quota_blocked=True).catalog())

    assert catalog.origin == CATALOG_ORIGIN_DESKTOP
    assert catalog.watchlist_name == snapshot.watchlist_name
    assert [section.name for section in catalog.sections] == [section.name for section in snapshot.sections]
    assert _visible_symbols(catalog) == _visible_symbols(snapshot)
    assert catalog.default_symbol == snapshot.default_symbol


def test_symbols_missing_from_the_visible_watchlist_are_left_out_of_the_list() -> None:
    snapshot = load_instrument_catalog()
    sequence = [row for row in _snapshot_sequence(snapshot) if row["symbol"] != "TVC:SILVER"]
    reader = FakeDesktopReader(sequence=sequence)

    catalog = asyncio.run(_source(reader, quota_blocked=True).catalog())

    assert "TVC:SILVER" not in _visible_symbols(catalog)
    assert catalog.origin == CATALOG_ORIGIN_DESKTOP


def test_visible_symbols_outside_the_snapshot_go_into_a_trailing_watchlist_section() -> None:
    snapshot = load_instrument_catalog()
    sequence = _snapshot_sequence(snapshot) + [{"symbol": "NASDAQ:AAPL"}]
    reader = FakeDesktopReader(sequence=sequence)

    catalog = asyncio.run(_source(reader, quota_blocked=True).catalog())

    assert catalog.sections[-1].name == "WATCHLIST"
    assert [item.symbol for item in catalog.sections[-1].instruments] == ["NASDAQ:AAPL"]


def test_a_visible_global_indices_watchlist_is_rejected_and_the_snapshot_is_used() -> None:
    global_rows = [
        {"symbol": item.symbol} for group in RECORDED_WATCHLIST_GROUPS for item in group.instruments
    ]
    reader = FakeDesktopReader(sequence=global_rows)

    catalog = asyncio.run(_source(reader, quota_blocked=True).catalog())

    assert catalog.origin == CATALOG_ORIGIN_SNAPSHOT
    assert catalog == load_instrument_catalog()


def test_a_failed_desktop_read_falls_back_to_the_snapshot() -> None:
    reader = FakeDesktopReader(error=DataSourceUnavailableError("Desktop bridge did not respond"))

    catalog = asyncio.run(_source(reader, quota_blocked=True).catalog())

    assert catalog.origin == CATALOG_ORIGIN_SNAPSHOT


def test_the_desktop_read_is_cached_for_five_minutes_even_when_it_fails() -> None:
    clock = Clock()
    reader = FakeDesktopReader(error=DataSourceUnavailableError("Desktop bridge did not respond"))
    source = _source(reader, quota_blocked=True, clock=clock)

    asyncio.run(source.catalog())
    asyncio.run(source.catalog())
    assert reader.calls == 1

    clock.now = START + timedelta(minutes=6)
    asyncio.run(source.catalog())
    assert reader.calls == 2


def test_the_global_market_section_source_rejects_the_commodity_watchlist() -> None:
    snapshot = load_instrument_catalog()
    reader = FakeDesktopReader(sequence=_snapshot_sequence(snapshot))

    with pytest.raises(WatchlistUnavailableError, match="PS_Global_Indices"):
        asyncio.run(DesktopWatchlistSectionSource(reader).read())


class _NoOrchestrator:
    async def get_context(self, *args, **kwargs):  # pragma: no cover - analysis is not reached in these tests
        raise AssertionError("the orchestrator must not be called for an unknown instrument")


def test_analysis_rejects_a_symbol_that_is_not_in_the_visible_watchlist() -> None:
    snapshot = load_instrument_catalog()
    sequence = [row for row in _snapshot_sequence(snapshot) if row["symbol"] != "TVC:SILVER"]
    service = MultiTimeframeAnalysisService(
        _NoOrchestrator(),
        catalog=snapshot,
        catalog_source=_source(FakeDesktopReader(sequence=sequence), quota_blocked=True),
    )

    assert asyncio.run(service.is_known("TVC:SILVER")) is False
    with pytest.raises(UnknownInstrumentError):
        asyncio.run(service.analyze("TVC:SILVER"))


def test_analysis_without_a_catalog_source_keeps_the_static_snapshot() -> None:
    service = MultiTimeframeAnalysisService(_NoOrchestrator())

    assert asyncio.run(service.is_known("PEPPERSTONE:NATGAS")) is True
    assert asyncio.run(service.current_catalog()) == load_instrument_catalog()
