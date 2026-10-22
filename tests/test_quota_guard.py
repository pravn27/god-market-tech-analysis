"""Official MCP daily quota: detection, the block until the reset, and the Desktop fallback end to end."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import asyncio

import pytest
from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.desktop_bridge import DesktopWatchlistQuote, DesktopWatchlistQuoteSnapshot
from god_market_api.global_market import RECORDED_WATCHLIST_GROUPS
from god_market_api.oauth import OfficialMCPOAuthCoordinator
from god_market_api.providers import (
    OfficialQuotaExceededError,
    is_quota_exceeded,
    next_quota_reset,
)

NOW = datetime(2026, 10, 22, 5, 36, tzinfo=timezone.utc)
QUOTA_TEXT = (
    "tool_pre_invoke blocked by plugin ToolQuotaPlugin: TOOL_QUOTA_EXCEEDED - Tool call quota exceeded "
    "(Daily tool-call quota for this user is exhausted. It resets at 00:00 UTC.)"
)


def _quota_result() -> object:
    return SimpleNamespace(isError=True, content=[SimpleNamespace(text=QUOTA_TEXT)])


def _ok_result() -> object:
    return SimpleNamespace(isError=False, content=[SimpleNamespace(text='{"bars": []}')])


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class NoStorage:
    async def get_tokens(self):
        return None


def _coordinator(clock: Clock) -> OfficialMCPOAuthCoordinator:
    return OfficialMCPOAuthCoordinator(storage=NoStorage(), clock=clock)


def test_quota_block_is_detected_from_the_mcp_result_text() -> None:
    assert is_quota_exceeded(_quota_result())
    assert not is_quota_exceeded(_ok_result())
    assert is_quota_exceeded({"isError": True, "content": QUOTA_TEXT})


def test_next_reset_is_the_following_midnight_utc() -> None:
    assert next_quota_reset(NOW) == datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)
    late = datetime(2026, 10, 22, 23, 59, tzinfo=timezone.utc)
    assert next_quota_reset(late) == datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)


def test_first_quota_block_stops_every_later_official_call_until_midnight(monkeypatch) -> None:
    asyncio.run(_quota_block_scenario(monkeypatch))


async def _quota_block_scenario(monkeypatch) -> None:
    clock = Clock(NOW)
    coordinator = _coordinator(clock)
    reached = []

    async def authorized(name, arguments):
        reached.append(name)
        return _quota_result()

    monkeypatch.setattr(coordinator, "_call_tool_authorized", authorized)

    with pytest.raises(OfficialQuotaExceededError, match="resume after 2026-10-23 00:00 UTC"):
        await coordinator.call_tool("mcp-tv-get-ohlcv", {"symbol": "TVC:SPX"})
    for _ in range(5):
        with pytest.raises(OfficialQuotaExceededError):
            await coordinator.call_tool("mcp-tv-get-ohlcv", {"symbol": "TVC:DJI"})

    assert reached == ["mcp-tv-get-ohlcv"]  # only the first call reached the MCP

    clock.now = datetime(2026, 10, 23, 0, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(coordinator, "_call_tool_authorized", _ok_async)
    assert await coordinator.call_tool("mcp-tv-get-ohlcv", {"symbol": "TVC:SPX"}) is not None


async def _ok_async(name, arguments):
    return _ok_result()


class _Desktop:
    """Desktop bridge stand-in: the recorded sections and a daily quote for every instrument."""

    def __init__(self) -> None:
        self.quote_calls = 0

    async def watchlist_payload(self):
        sequence = []
        for group in RECORDED_WATCHLIST_GROUPS:
            sequence.append({"section": group.name})
            sequence.extend({"symbol": item.symbol} for item in group.instruments)
        return {"success": True, "sequence": sequence}

    async def get_quotes(self, expected_symbols):
        self.quote_calls += 1
        quotes = {symbol: DesktopWatchlistQuote(last_price=100.0, change_percent=0.5) for symbol in expected_symbols}
        return DesktopWatchlistQuoteSnapshot(quotes=quotes, observed_at=NOW)


def test_quota_exhaustion_falls_back_to_desktop_and_spends_one_official_call(monkeypatch) -> None:
    clock = Clock(NOW)
    coordinator = _coordinator(clock)
    reached = []

    async def authorized(name, arguments):
        reached.append(name)
        return _quota_result()

    monkeypatch.setattr(coordinator, "_call_tool_authorized", authorized)
    desktop = _Desktop()
    client = TestClient(create_app(oauth=coordinator, desktop_watchlist_reader=desktop))

    response = client.get("/api/v1/global-market-sentiment", params={"timeframe": "1D"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["desktop_fallback"] == "full"
    instruments = [item for group in payload["groups"] for item in group["instruments"]]
    assert instruments and all(item["source"] == "desktop_bridge" for item in instruments)
    assert all(item["change_percent"] == 0.5 for item in instruments)
    assert any("TradingView MCP watchlist unavailable" in warning for warning in payload["warnings"])
    # One official call reached the MCP; the block stopped every other official request.
    assert len(reached) == 1
    assert desktop.quote_calls == 1
