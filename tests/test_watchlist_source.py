"""Tests for reading the Global Market watchlist sections from the official TradingView MCP."""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from god_market_api.global_market import (
    GlobalMarketLiveSnapshotProvider,
    RECORDED_WATCHLIST_GROUPS,
    RECORDED_WATCHLIST_WARNING,
    WatchlistUnavailableError,
)
from god_market_api.models import ChartContext
from god_market_api.providers import DataSourceUnavailableError
from god_market_api.watchlist_source import (
    LIST_WATCHLISTS_TOOL,
    OfficialWatchlistSource,
    parse_watchlist_groups,
)


NOW = datetime(2026, 10, 17, 9, 30, tzinfo=timezone.utc)


def _payload(*watchlists: tuple[str, list[str]]) -> SimpleNamespace:
    body = {"watchlists": [{"name": name, "symbols": symbols} for name, symbols in watchlists]}
    return SimpleNamespace(isError=False, content=[SimpleNamespace(type="text", text=json.dumps(body))])


class FakeMCP:
    """Records every tool call. ``responses`` are returned in order; an Exception is raised instead."""

    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        response = self.responses[0] if len(self.responses) == 1 else self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def test_parse_splits_sections_at_headers_and_drops_empty_ones() -> None:
    groups = parse_watchlist_groups(
        ["###USA", "TVC:SPX", "NYSE:INFY", "###EMPTY", "###INDIA ADRS", "NYSE:HDB"],
        display_names={"NYSE:HDB": "HDFC Bank ADR"},
    )

    assert [(group.name, [item.symbol for item in group.instruments]) for group in groups] == [
        ("USA", ["TVC:SPX", "NYSE:INFY"]),
        ("INDIA ADRS", ["NYSE:HDB"]),
    ]
    assert groups[1].instruments[0].display_name == "HDFC Bank ADR"
    assert groups[0].instruments[0].display_name == "SPX"  # unknown symbols show their ticker


def test_symbols_before_the_first_header_go_to_the_watchlist_section() -> None:
    groups = parse_watchlist_groups(["TVC:DJI", "###USA", "TVC:SPX"])

    assert [group.name for group in groups] == ["WATCHLIST", "USA"]


def test_reads_the_named_watchlist_through_the_list_tool_only() -> None:
    mcp = FakeMCP(
        _payload(
            ("Other", ["NASDAQ:AAPL"]),
            ("PS_Global_Indices", ["###USA", "TVC:SPX", "###INDIA ADRS", "NYSE:HDB"]),
        )
    )
    source = OfficialWatchlistSource(mcp, clock=Clock(NOW))

    read = asyncio.run(source.read())

    assert mcp.calls == [(LIST_WATCHLISTS_TOOL, {})]
    assert read.error is None
    assert read.read_at == NOW
    assert [group.name for group in read.groups] == ["USA", "INDIA ADRS"]


def test_reuses_the_reading_until_the_cache_expires() -> None:
    clock = Clock(NOW)
    mcp = FakeMCP(_payload(("PS_Global_Indices", ["###USA", "TVC:SPX"])))
    source = OfficialWatchlistSource(mcp, clock=clock, cache_for=timedelta(minutes=5))

    asyncio.run(source.read())
    clock.now = NOW + timedelta(minutes=4)
    asyncio.run(source.read())
    assert len(mcp.calls) == 1

    clock.now = NOW + timedelta(minutes=6)
    asyncio.run(source.read())
    assert len(mcp.calls) == 2


def test_a_failed_refresh_keeps_the_last_good_reading_and_says_why() -> None:
    clock = Clock(NOW)
    mcp = FakeMCP(
        _payload(("PS_Global_Indices", ["###USA", "TVC:SPX"])),
        RuntimeError("MCP session expired"),
    )
    source = OfficialWatchlistSource(mcp, clock=clock, cache_for=timedelta(minutes=5))

    asyncio.run(source.read())
    clock.now = NOW + timedelta(minutes=10)
    read = asyncio.run(source.read())

    assert [group.name for group in read.groups] == ["USA"]
    assert read.read_at == NOW
    assert read.error == "MCP session expired"


def test_a_failed_first_read_raises_so_the_caller_can_fall_back() -> None:
    source = OfficialWatchlistSource(FakeMCP(RuntimeError("MCP unavailable")), clock=Clock(NOW))

    with pytest.raises(WatchlistUnavailableError, match="MCP unavailable"):
        asyncio.run(source.read())


def test_a_missing_watchlist_is_reported_not_guessed() -> None:
    source = OfficialWatchlistSource(FakeMCP(_payload(("Other", ["NASDAQ:AAPL"]))), clock=Clock(NOW))

    with pytest.raises(WatchlistUnavailableError, match="PS_Global_Indices was not found"):
        asyncio.run(source.read())


def test_an_error_result_from_the_tool_is_treated_as_a_failure() -> None:
    error_result = SimpleNamespace(isError=True, content=[SimpleNamespace(type="text", text="denied")])
    source = OfficialWatchlistSource(FakeMCP(error_result), clock=Clock(NOW))

    with pytest.raises(WatchlistUnavailableError):
        asyncio.run(source.read())


class NoPriceProvider:
    """Every price request is unavailable, so the snapshot exposes only the watchlist sections and warnings."""

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        raise DataSourceUnavailableError(f"{symbol} is unavailable")


class StaticWatchlistSource:
    def __init__(self, result: Any) -> None:
        self.result = result

    async def read(self) -> Any:
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _snapshot(source: Any | None):
    provider = GlobalMarketLiveSnapshotProvider(
        NoPriceProvider(), watchlist_source=source, clock=lambda: NOW, retry_attempts=0
    )
    return asyncio.run(provider.get_snapshot("daily"))


def test_provider_without_a_source_keeps_the_recorded_snapshot_warning() -> None:
    snapshot = _snapshot(None)

    assert snapshot.warnings[1] == RECORDED_WATCHLIST_WARNING
    assert [group.name for group in snapshot.groups] == [group.name for group in RECORDED_WATCHLIST_GROUPS]


def test_provider_shows_live_sections_read_from_tradingview() -> None:
    from god_market_api.global_market import WatchlistRead, WatchlistGroupDefinition, WatchlistInstrumentDefinition

    live_groups = (
        WatchlistGroupDefinition("USA", (WatchlistInstrumentDefinition("TVC:SPX", "S&P 500"),)),
        WatchlistGroupDefinition("INDIA ADRS", (WatchlistInstrumentDefinition("NYSE:RDY", "Dr. Reddy's ADR"),)),
    )
    snapshot = _snapshot(StaticWatchlistSource(WatchlistRead(groups=live_groups, read_at=NOW)))

    assert snapshot.warnings[1] == "Watchlist groups read live from TradingView PS_Global_Indices at 09:30 UTC."
    assert [group.name for group in snapshot.groups] == ["USA", "INDIA ADRS"]
    assert [item.symbol for group in snapshot.groups for item in group.instruments] == ["TVC:SPX", "NYSE:RDY"]


def test_provider_says_when_a_refresh_failed_and_older_groups_are_shown() -> None:
    from god_market_api.global_market import WatchlistRead, WatchlistGroupDefinition, WatchlistInstrumentDefinition

    old_groups = (WatchlistGroupDefinition("USA", (WatchlistInstrumentDefinition("TVC:SPX", "S&P 500"),)),)
    read = WatchlistRead(groups=old_groups, read_at=NOW - timedelta(hours=1), error="MCP session expired")
    snapshot = _snapshot(StaticWatchlistSource(read))

    assert snapshot.warnings[1] == (
        "TradingView watchlist refresh failed (MCP session expired); showing groups read at 08:30 UTC."
    )
    assert [group.name for group in snapshot.groups] == ["USA"]


def test_provider_falls_back_to_the_recorded_groups_when_the_watchlist_cannot_be_read() -> None:
    snapshot = _snapshot(StaticWatchlistSource(WatchlistUnavailableError("MCP unavailable")))

    assert snapshot.warnings[1] == (
        "TradingView watchlist could not be read (MCP unavailable); showing the recorded 2026-10-07 snapshot."
    )
    assert [group.name for group in snapshot.groups] == [group.name for group in RECORDED_WATCHLIST_GROUPS]


def test_provider_says_the_sections_came_from_the_desktop_when_the_mcp_is_unavailable() -> None:
    from god_market_api.global_market import WATCHLIST_ORIGIN_DESKTOP, WatchlistRead

    read = WatchlistRead(
        groups=RECORDED_WATCHLIST_GROUPS, read_at=NOW, error="MCP session expired", origin=WATCHLIST_ORIGIN_DESKTOP
    )
    snapshot = _snapshot(StaticWatchlistSource(read))

    assert snapshot.warnings[1] == (
        "TradingView MCP watchlist unavailable (MCP session expired); sections read from TradingView Desktop at 09:30 UTC."
    )
