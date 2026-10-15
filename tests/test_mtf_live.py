"""Live multi-timeframe feed: refresh schedule, shared loop, and the WebSocket route."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.models import AnalysisTimeframe, ChartContext, DataSource, SourceHealth, SourceState
from god_market_api.mtf_analysis import MultiTimeframeAnalysisService
from god_market_api.mtf_live import LiveSchedule, MtfLiveHub, next_refresh_at
from god_market_api.mtf_orchestrator import MultiTimeframeContextOrchestrator

IST = timezone(timedelta(hours=5, minutes=30))
SCHEDULE = LiveSchedule()
FAST = LiveSchedule(
    forming_interval=timedelta(milliseconds=50),
    retry_interval=timedelta(milliseconds=50),
    retry_limit=5,
    idle_interval=timedelta(milliseconds=50),
)
NSE_DAILY_OPEN = datetime(2026, 10, 15, 9, 15, tzinfo=IST)  # closes 15:30 IST
SYMBOL = "PEPPERSTONE:NATGAS"


# Schedule rules


def test_forming_candle_refreshes_every_minute_while_it_is_still_open():
    now = datetime(2026, 10, 15, 10, 0, tzinfo=IST)
    due = next_refresh_at(AnalysisTimeframe.DAILY, NSE_DAILY_OPEN, now, "NSE", 0, SCHEDULE)
    assert due == now + timedelta(seconds=60)


def test_refresh_is_pulled_forward_to_the_candle_close_boundary():
    now = datetime(2026, 10, 15, 15, 29, 30, tzinfo=IST)
    due = next_refresh_at(AnalysisTimeframe.DAILY, NSE_DAILY_OPEN, now, "NSE", 0, SCHEDULE)
    assert due == datetime(2026, 10, 15, 15, 30, tzinfo=IST)


def test_after_close_the_source_is_retried_each_minute_then_idles():
    after_close = datetime(2026, 10, 15, 15, 31, tzinfo=IST)
    retrying = next_refresh_at(AnalysisTimeframe.DAILY, NSE_DAILY_OPEN, after_close, "NSE", 2, SCHEDULE)
    idle = next_refresh_at(AnalysisTimeframe.DAILY, NSE_DAILY_OPEN, after_close, "NSE", 5, SCHEDULE)
    assert retrying == after_close + timedelta(seconds=60)
    assert idle == after_close + timedelta(minutes=10)


def test_missing_candle_is_retried_not_treated_as_live():
    now = datetime(2026, 10, 15, 10, 0, tzinfo=IST)
    assert next_refresh_at(AnalysisTimeframe.DAILY, None, now, "NSE", 0, SCHEDULE) == now + timedelta(seconds=60)


# Shared loop


class AdvancingFixtureProvider:
    """Returns a fixed or advancing latest-candle timestamp; no candle bodies, so checklists are unavailable."""

    def __init__(self, advance: bool) -> None:
        self.advance = advance
        self.calls = 0

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source=DataSource.OFFICIAL_MCP,
            state=SourceState.READY,
            detail="Test provider is ready.",
            checked_at=datetime.now(timezone.utc),
        )

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        self.calls += 1
        opened = NSE_DAILY_OPEN + (timedelta(days=self.calls) if self.advance else timedelta())
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=opened,
            freshness_state=SourceState.READY,
        )


def _hub(provider: AdvancingFixtureProvider) -> MtfLiveHub:
    orchestrator = MultiTimeframeContextOrchestrator(provider)
    service = MultiTimeframeAnalysisService(orchestrator)
    return MtfLiveHub(service, orchestrator, schedule=FAST, heartbeat_interval=timedelta(seconds=5))


def test_subscriber_gets_a_snapshot_then_forming_refresh_updates():
    async def scenario() -> None:
        hub = _hub(AdvancingFixtureProvider(advance=False))
        queue = hub.subscribe(SYMBOL)
        snapshot = await asyncio.wait_for(queue.get(), 5)
        update = await asyncio.wait_for(queue.get(), 5)
        assert snapshot.version == 1 and snapshot.type == "snapshot" and snapshot.reason == "subscribed"
        assert snapshot.analysis is not None and snapshot.analysis.symbol == SYMBOL
        assert update.type == "update" and update.reason == "forming_refresh" and update.closed_timeframes == []
        hub.unsubscribe(SYMBOL, queue)
        assert SYMBOL not in hub._tasks

    asyncio.run(scenario())


def test_new_candle_from_the_source_is_reported_as_a_candle_close():
    async def scenario() -> None:
        hub = _hub(AdvancingFixtureProvider(advance=True))
        queue = hub.subscribe(SYMBOL)
        await asyncio.wait_for(queue.get(), 5)  # snapshot
        update = await asyncio.wait_for(queue.get(), 5)
        assert update.reason == "candle_close"
        assert update.closed_timeframes
        hub.unsubscribe(SYMBOL, queue)

    asyncio.run(scenario())


def test_subscribers_share_one_loop_until_the_last_one_leaves():
    async def scenario() -> None:
        hub = _hub(AdvancingFixtureProvider(advance=False))
        first = hub.subscribe(SYMBOL)
        second = hub.subscribe(SYMBOL)
        assert len(hub._tasks) == 1
        hub.unsubscribe(SYMBOL, first)
        assert SYMBOL in hub._tasks
        hub.unsubscribe(SYMBOL, second)
        assert SYMBOL not in hub._tasks

    asyncio.run(scenario())


# WebSocket route


def _client(heartbeat_ms: int = 50_000) -> TestClient:
    provider = AdvancingFixtureProvider(advance=False)
    orchestrator = MultiTimeframeContextOrchestrator(provider)
    service = MultiTimeframeAnalysisService(orchestrator)
    hub = MtfLiveHub(service, orchestrator, heartbeat_interval=timedelta(milliseconds=heartbeat_ms))
    return TestClient(create_app(provider=provider, mtf_orchestrator=orchestrator, mtf_analysis=service, mtf_live=hub))


def test_live_socket_rejects_an_instrument_outside_the_watchlist():
    with pytest.raises(WebSocketDisconnect):
        with _client().websocket_connect("/api/v1/mtf-analysis/NOT%3AAREAL/live"):
            pass


def test_live_socket_sends_a_versioned_snapshot_first():
    with _client().websocket_connect("/api/v1/mtf-analysis/PEPPERSTONE%3ANATGAS/live") as socket:
        message = socket.receive_json()
    assert message["version"] == 1
    assert message["type"] == "snapshot"
    assert message["symbol"] == SYMBOL
    assert message["analysis"]["symbol"] == SYMBOL


def test_live_socket_sends_heartbeats_when_nothing_changes():
    with _client(heartbeat_ms=50).websocket_connect("/api/v1/mtf-analysis/PEPPERSTONE%3ANATGAS/live") as socket:
        socket.receive_json()  # snapshot
        assert socket.receive_json()["type"] == "heartbeat"
