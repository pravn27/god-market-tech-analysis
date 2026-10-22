"""Local live feed for the Global Market page (WebSocket protocol v1).

Like the multi-timeframe feed, the backend talks to the market-data sources, not the browser. One
refresh loop per timeframe serves every dashboard subscribed to it, so several open tabs cost one
set of source calls. Each refresh bypasses the snapshot cache, so every update is a fresh read.

Nothing here uses TradingView's internal chart WebSocket.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, Optional, Protocol

from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from .models import GlobalMarketSnapshot
from .mtf_live import wait_for_client_disconnect

PROTOCOL_VERSION = 1
QUEUE_LIMIT = 4
LIVE_DISABLED_MESSAGE = "Live updates are disabled on the server; use Refresh Data."


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SnapshotSource(Protocol):
    async def get_snapshot(self, timeframe: str, *, force_refresh: bool = False) -> GlobalMarketSnapshot:
        ...


class GlobalMarketLiveEnvelope(BaseModel):
    """One message on the live socket. ``snapshot`` is set for snapshot and update messages."""

    version: int = PROTOCOL_VERSION
    type: Literal["snapshot", "update", "heartbeat", "error"]
    timeframe: str
    sent_at: datetime
    snapshot: Optional[GlobalMarketSnapshot] = None
    error: Optional[str] = None


@dataclass(frozen=True)
class GlobalMarketLiveSchedule:
    # One refresh reads every instrument from the official MCP, so five minutes keeps the daily quota usable.
    refresh_interval: timedelta = timedelta(minutes=5)
    heartbeat_interval: timedelta = timedelta(seconds=30)


class GlobalMarketLiveHub:
    """Shares one refresh loop per timeframe among all of its WebSocket subscribers."""

    def __init__(
        self,
        provider: SnapshotSource,
        *,
        schedule: GlobalMarketLiveSchedule = GlobalMarketLiveSchedule(),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._provider = provider
        self._schedule = schedule
        self._clock = clock
        self._subscribers: dict[str, set[asyncio.Queue[GlobalMarketLiveEnvelope]]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def heartbeat_seconds(self) -> float:
        return self._schedule.heartbeat_interval.total_seconds()

    def subscribe(self, timeframe: str) -> "asyncio.Queue[GlobalMarketLiveEnvelope]":
        queue: asyncio.Queue[GlobalMarketLiveEnvelope] = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._subscribers.setdefault(timeframe, set()).add(queue)
        task = self._tasks.get(timeframe)
        if task is None or task.done():
            self._tasks[timeframe] = asyncio.create_task(self._run(timeframe))
        return queue

    def unsubscribe(self, timeframe: str, queue: "asyncio.Queue[GlobalMarketLiveEnvelope]") -> None:
        subscribers = self._subscribers.get(timeframe)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(timeframe, None)
            task = self._tasks.pop(timeframe, None)
            if task is not None:
                task.cancel()

    def heartbeat(self, timeframe: str) -> GlobalMarketLiveEnvelope:
        return GlobalMarketLiveEnvelope(type="heartbeat", timeframe=timeframe, sent_at=self._clock())

    def _publish(self, timeframe: str, envelope: GlobalMarketLiveEnvelope) -> None:
        for queue in list(self._subscribers.get(timeframe, ())):
            if queue.full():
                # Drop the oldest message so a slow client always receives the newest state.
                queue.get_nowait()
            queue.put_nowait(envelope)

    async def _run(self, timeframe: str) -> None:
        """Refresh loop for one timeframe; cancelled by ``unsubscribe`` when the last subscriber leaves."""
        first = True
        while True:
            if not first:
                await asyncio.sleep(self._schedule.refresh_interval.total_seconds())
            # The first read may use the cache so a new subscriber gets the current page at once.
            force_refresh = not first
            first = False
            try:
                snapshot = await self._provider.get_snapshot(timeframe, force_refresh=force_refresh)
            except Exception:
                self._publish(timeframe, self._error(timeframe, "Live refresh failed; retrying shortly."))
                continue
            kind: Literal["snapshot", "update"] = "update" if force_refresh else "snapshot"
            self._publish(
                timeframe,
                GlobalMarketLiveEnvelope(type=kind, timeframe=timeframe, sent_at=self._clock(), snapshot=snapshot),
            )

    def _error(self, timeframe: str, message: str) -> GlobalMarketLiveEnvelope:
        return GlobalMarketLiveEnvelope(type="error", timeframe=timeframe, sent_at=self._clock(), error=message)


async def reject_global_market_live(websocket: WebSocket, timeframe: str) -> None:
    """Tell the client live updates are off, then close with 1008 so it stops reconnecting.

    No refresh loop is started, so a rejected client costs no source calls.
    """
    envelope = GlobalMarketLiveEnvelope(
        type="error", timeframe=timeframe, sent_at=_utc_now(), error=LIVE_DISABLED_MESSAGE
    )
    await websocket.send_json(envelope.model_dump(mode="json"))
    await websocket.close(code=1008, reason="Live updates are disabled.")


async def relay_global_market_live(websocket: WebSocket, hub: GlobalMarketLiveHub, timeframe: str) -> None:
    """Send the hub's envelopes for one timeframe until the client leaves."""
    queue = hub.subscribe(timeframe)
    watcher = asyncio.create_task(wait_for_client_disconnect(websocket))
    getter: Optional[asyncio.Task] = None
    try:
        while not watcher.done():
            getter = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {getter, watcher},
                timeout=hub.heartbeat_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if watcher.done():
                break
            if getter in done:
                envelope = getter.result()
            else:
                getter.cancel()
                envelope = hub.heartbeat(timeframe)
            await websocket.send_json(envelope.model_dump(mode="json"))
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        watcher.cancel()
        if getter is not None and not getter.done():
            getter.cancel()
        hub.unsubscribe(timeframe, queue)
