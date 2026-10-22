"""Global Market live feed: shared refresh loop, forced refresh, and the WebSocket route."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.global_market import GlobalMarketLiveSnapshotProvider
from god_market_api.global_market_live import GlobalMarketLiveHub, GlobalMarketLiveSchedule
from god_market_api.models import (
    GlobalMarketBreadth,
    GlobalMarketCompleteness,
    GlobalMarketSnapshot,
)

NOW = datetime(2026, 10, 22, 4, 0, tzinfo=timezone.utc)
FAST = GlobalMarketLiveSchedule(refresh_interval=timedelta(milliseconds=30), heartbeat_interval=timedelta(seconds=5))


class CountingSnapshotProvider:
    """Returns a snapshot whose warning records how many reads happened and whether they were forced."""

    def __init__(self, *, fail_after: int | None = None) -> None:
        self.calls: list[tuple[str, bool]] = []
        self.fail_after = fail_after

    async def get_snapshot(self, timeframe: str, *, force_refresh: bool = False) -> GlobalMarketSnapshot:
        self.calls.append((timeframe, force_refresh))
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise RuntimeError("source went away")
        return GlobalMarketSnapshot(
            watchlist_name="PS_Global_Indices",
            read_at=NOW,
            timeframe=timeframe,
            completeness=GlobalMarketCompleteness.COMPLETE,
            groups=[],
            breadth=GlobalMarketBreadth(advancing=0, declining=0, unchanged=0, unavailable=0),
            warnings=[f"read {len(self.calls)}"],
        )


def test_subscriber_gets_a_cached_snapshot_then_forced_updates() -> None:
    async def scenario() -> None:
        provider = CountingSnapshotProvider()
        hub = GlobalMarketLiveHub(provider, schedule=FAST)
        queue = hub.subscribe("1D")
        first = await asyncio.wait_for(queue.get(), 5)
        second = await asyncio.wait_for(queue.get(), 5)
        assert first.type == "snapshot" and first.snapshot is not None and first.timeframe == "1D"
        assert second.type == "update" and second.snapshot is not None
        assert provider.calls[0] == ("1D", False)
        assert provider.calls[1] == ("1D", True)
        hub.unsubscribe("1D", queue)
        assert "1D" not in hub._tasks

    asyncio.run(scenario())


def test_subscribers_share_one_loop_per_timeframe_until_the_last_one_leaves() -> None:
    async def scenario() -> None:
        provider = CountingSnapshotProvider()
        hub = GlobalMarketLiveHub(provider, schedule=FAST)
        first = hub.subscribe("1D")
        second = hub.subscribe("1D")
        await asyncio.wait_for(first.get(), 5)
        assert len(hub._tasks) == 1
        hub.unsubscribe("1D", first)
        assert "1D" in hub._tasks
        await asyncio.wait_for(second.get(), 5)
        hub.unsubscribe("1D", second)
        assert "1D" not in hub._tasks

    asyncio.run(scenario())


def test_each_timeframe_gets_its_own_loop() -> None:
    async def scenario() -> None:
        provider = CountingSnapshotProvider()
        hub = GlobalMarketLiveHub(provider, schedule=FAST)
        daily = hub.subscribe("1D")
        weekly = hub.subscribe("1W")
        first_daily = await asyncio.wait_for(daily.get(), 5)
        first_weekly = await asyncio.wait_for(weekly.get(), 5)
        assert first_daily.timeframe == "1D" and first_weekly.timeframe == "1W"
        hub.unsubscribe("1D", daily)
        hub.unsubscribe("1W", weekly)

    asyncio.run(scenario())


def test_source_failure_is_reported_and_the_loop_keeps_running() -> None:
    async def scenario() -> None:
        provider = CountingSnapshotProvider(fail_after=1)
        hub = GlobalMarketLiveHub(provider, schedule=FAST)
        queue = hub.subscribe("1D")
        await asyncio.wait_for(queue.get(), 5)  # first snapshot
        error = await asyncio.wait_for(queue.get(), 5)
        assert error.type == "error" and error.snapshot is None
        assert error.error == "Live refresh failed; retrying shortly."
        hub.unsubscribe("1D", queue)

    asyncio.run(scenario())


def test_live_provider_bypasses_the_snapshot_cache_only_when_forced() -> None:
    async def scenario() -> None:
        provider = GlobalMarketLiveSnapshotProvider.__new__(GlobalMarketLiveSnapshotProvider)
        cached = GlobalMarketSnapshot(
            watchlist_name="PS_Global_Indices",
            read_at=NOW,
            timeframe="1D",
            completeness=GlobalMarketCompleteness.COMPLETE,
            groups=[],
            breadth=GlobalMarketBreadth(advancing=0, declining=0, unchanged=0, unavailable=0),
        )
        provider._cached_snapshot = lambda timeframe: cached  # type: ignore[method-assign]
        assert await provider.get_snapshot("1D") is cached
        # A forced read must not return the cached value; it proceeds past the cache check.
        provider._snapshot_lock = asyncio.Lock()
        provider._resolve_watchlist = _raise_after_cache_check  # type: ignore[method-assign]
        try:
            await provider.get_snapshot("1D", force_refresh=True)
        except _Reached:
            pass
        else:  # pragma: no cover - the forced path must not return the cached value
            raise AssertionError("forced refresh returned the cached snapshot")

    asyncio.run(scenario())


class _Reached(Exception):
    pass


async def _raise_after_cache_check() -> None:
    raise _Reached


def _client(heartbeat_ms: int = 50_000, provider: CountingSnapshotProvider | None = None) -> TestClient:
    provider = provider or CountingSnapshotProvider()
    hub = GlobalMarketLiveHub(
        provider,
        schedule=GlobalMarketLiveSchedule(
            refresh_interval=timedelta(seconds=60),
            heartbeat_interval=timedelta(milliseconds=heartbeat_ms),
        ),
    )
    return TestClient(create_app(global_market_provider=provider, global_market_live=hub))


def test_live_socket_sends_a_versioned_snapshot_first() -> None:
    with _client().websocket_connect("/api/v1/global-market-sentiment/live?timeframe=1D") as socket:
        message = socket.receive_json()
    assert message["version"] == 1
    assert message["type"] == "snapshot"
    assert message["timeframe"] == "1D"
    assert message["snapshot"]["timeframe"] == "1D"


def test_live_socket_normalizes_dashboard_timeframe_labels() -> None:
    with _client().websocket_connect("/api/v1/global-market-sentiment/live?timeframe=daily") as socket:
        message = socket.receive_json()
    assert message["timeframe"] == "1D"


def test_live_socket_rejects_an_unsupported_timeframe() -> None:
    with pytest.raises(WebSocketDisconnect):
        with _client().websocket_connect("/api/v1/global-market-sentiment/live?timeframe=2h"):
            pass


def test_live_socket_sends_heartbeats_when_nothing_changes() -> None:
    with _client(heartbeat_ms=50).websocket_connect("/api/v1/global-market-sentiment/live?timeframe=1D") as socket:
        socket.receive_json()  # snapshot
        assert socket.receive_json()["type"] == "heartbeat"
