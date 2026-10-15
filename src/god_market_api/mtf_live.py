"""Local live feed for the multi-timeframe checklist (WebSocket protocol v1).

The backend, not the browser, talks to the market-data source. One refresh loop per symbol
serves every dashboard subscribed to it, so several open tabs cost one set of source calls.

Refresh timing follows the candle schedule in ``mtf_analysis``:

- A candle that is still forming is re-fetched every ``forming_interval``.
- When a candle's session closes, its timeframe is re-fetched at the boundary. If the source
  has not published the next candle yet, retries follow ``retry_interval`` up to
  ``retry_limit`` attempts, then ``idle_interval`` until a new candle appears.

Nothing here uses TradingView's internal chart WebSocket; every refresh goes through the
existing orchestrator and its configured source.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Literal, Optional

from fastapi import WebSocket
from pydantic import BaseModel, Field

from .models import AnalysisTimeframe, MultiTimeframeAnalysis, default_mtf_timeframes
from .mtf_analysis import MultiTimeframeAnalysisService, candle_closes_at, exchange_of
from .mtf_orchestrator import MultiTimeframeContextOrchestrator

PROTOCOL_VERSION = 1
QUEUE_LIMIT = 4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class LiveSchedule:
    """Refresh cadence; defaults are recorded in the specification."""

    forming_interval: timedelta = timedelta(seconds=60)
    retry_interval: timedelta = timedelta(seconds=60)
    retry_limit: int = 5
    idle_interval: timedelta = timedelta(minutes=10)


class LiveEnvelope(BaseModel):
    """One message on the live socket. ``analysis`` is set for snapshot and update messages."""

    version: int = PROTOCOL_VERSION
    type: Literal["snapshot", "update", "heartbeat", "error"]
    symbol: str
    sent_at: datetime
    reason: Optional[Literal["subscribed", "candle_close", "forming_refresh"]] = None
    closed_timeframes: list[AnalysisTimeframe] = Field(default_factory=list)
    analysis: Optional[MultiTimeframeAnalysis] = None
    error: Optional[str] = None


@dataclass
class _Track:
    """Schedule state for one timeframe: the latest candle seen and when to refresh it next."""

    opened_at: Optional[datetime]
    next_refresh_at: datetime
    retries: int = 0


def next_refresh_at(
    timeframe: AnalysisTimeframe,
    opened_at: Optional[datetime],
    now: datetime,
    exchange: str,
    retries: int,
    schedule: LiveSchedule,
) -> datetime:
    """When to re-fetch one timeframe, given its latest candle open time and recent failed retries."""
    if opened_at is None:
        return now + (schedule.retry_interval if retries < schedule.retry_limit else schedule.idle_interval)
    closes_at = candle_closes_at(timeframe, opened_at, exchange)
    if now < closes_at:
        return min(now + schedule.forming_interval, closes_at)
    return now + (schedule.retry_interval if retries < schedule.retry_limit else schedule.idle_interval)


class MtfLiveHub:
    """Shares one refresh loop per subscribed symbol among all of its WebSocket subscribers."""

    def __init__(
        self,
        service: MultiTimeframeAnalysisService,
        orchestrator: MultiTimeframeContextOrchestrator,
        *,
        schedule: LiveSchedule = LiveSchedule(),
        heartbeat_interval: timedelta = timedelta(seconds=30),
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._service = service
        self._orchestrator = orchestrator
        self._schedule = schedule
        self._heartbeat_interval = heartbeat_interval
        self._clock = clock
        self._subscribers: dict[str, set[asyncio.Queue[LiveEnvelope]]] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def heartbeat_seconds(self) -> float:
        return self._heartbeat_interval.total_seconds()

    def subscribe(self, symbol: str) -> "asyncio.Queue[LiveEnvelope]":
        queue: asyncio.Queue[LiveEnvelope] = asyncio.Queue(maxsize=QUEUE_LIMIT)
        self._subscribers.setdefault(symbol, set()).add(queue)
        task = self._tasks.get(symbol)
        if task is None or task.done():
            self._tasks[symbol] = asyncio.create_task(self._run(symbol))
        return queue

    def unsubscribe(self, symbol: str, queue: "asyncio.Queue[LiveEnvelope]") -> None:
        subscribers = self._subscribers.get(symbol)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(symbol, None)
            task = self._tasks.pop(symbol, None)
            if task is not None:
                task.cancel()

    def heartbeat(self, symbol: str) -> LiveEnvelope:
        return LiveEnvelope(type="heartbeat", symbol=symbol, sent_at=self._clock())

    def _publish(self, symbol: str, envelope: LiveEnvelope) -> None:
        for queue in list(self._subscribers.get(symbol, ())):
            if queue.full():
                # Drop the oldest message so a slow client always receives the newest state.
                queue.get_nowait()
            queue.put_nowait(envelope)

    def _track(self, timeframe: AnalysisTimeframe, analysis: MultiTimeframeAnalysis, now: datetime) -> _Track:
        status = analysis.timeframes.get(timeframe)
        opened_at = status.source_timestamp if status else None
        exchange = exchange_of(analysis.symbol)
        return _Track(
            opened_at=opened_at,
            next_refresh_at=next_refresh_at(timeframe, opened_at, now, exchange, 0, self._schedule),
        )

    async def _run(self, symbol: str) -> None:
        """Refresh loop for one symbol; cancelled by ``unsubscribe`` when the last subscriber leaves."""
        timeframes = default_mtf_timeframes()
        exchange = exchange_of(symbol)
        try:
            analysis = await self._service.analyze(symbol)
        except Exception:
            self._publish(symbol, self._error(symbol, "Market data is unavailable; reconnect to retry."))
            return
        now = self._clock()
        tracks = {tf: self._track(tf, analysis, now) for tf in timeframes}
        self._publish(symbol, self._envelope(symbol, "snapshot", "subscribed", analysis))
        while True:
            wake_at = min(track.next_refresh_at for track in tracks.values())
            await asyncio.sleep(max(0.0, (wake_at - self._clock()).total_seconds()))
            now = self._clock()
            due = [tf for tf, track in tracks.items() if track.next_refresh_at <= now]
            if not due:
                continue
            try:
                await self._orchestrator.get_context(symbol, timeframes=due, force_refresh=True)
                analysis = await self._service.analyze(symbol)
            except Exception:
                self._publish(symbol, self._error(symbol, "Live refresh failed; retrying shortly."))
                for tf in due:
                    tracks[tf].next_refresh_at = now + self._schedule.retry_interval
                continue
            closed: list[AnalysisTimeframe] = []
            for tf in due:
                track = tracks[tf]
                status = analysis.timeframes.get(tf)
                latest = status.source_timestamp if status else None
                if latest != track.opened_at:
                    if track.opened_at is not None and latest is not None:
                        closed.append(tf)
                    track.opened_at = latest
                    track.retries = 0
                elif track.opened_at is None or now >= candle_closes_at(tf, track.opened_at, exchange):
                    track.retries += 1
                track.next_refresh_at = next_refresh_at(
                    tf, track.opened_at, now, exchange, track.retries, self._schedule
                )
            reason = "candle_close" if closed else "forming_refresh"
            self._publish(symbol, self._envelope(symbol, "update", reason, analysis, closed))

    def _envelope(
        self,
        symbol: str,
        kind: Literal["snapshot", "update"],
        reason: Literal["subscribed", "candle_close", "forming_refresh"],
        analysis: MultiTimeframeAnalysis,
        closed: list[AnalysisTimeframe] | None = None,
    ) -> LiveEnvelope:
        return LiveEnvelope(
            type=kind,
            symbol=symbol,
            sent_at=self._clock(),
            reason=reason,
            closed_timeframes=closed or [],
            analysis=analysis,
        )

    def _error(self, symbol: str, message: str) -> LiveEnvelope:
        return LiveEnvelope(type="error", symbol=symbol, sent_at=self._clock(), error=message)


async def wait_for_client_disconnect(websocket: WebSocket) -> None:
    """Return once the client has closed the socket; used to stop the sender loop promptly."""
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return
