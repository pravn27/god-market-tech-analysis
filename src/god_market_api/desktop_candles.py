"""Candles from the chart open in TradingView Desktop, used only when the official MCP fails.

The bridge reads bars only from the chart on screen. Each read therefore switches that chart to the
requested symbol and interval, reads the bars, and restores the symbol and interval the user had open.
Reads are serialized because there is one chart, and short-lived results are reused so a failing MCP
does not switch the user's chart on every request.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Protocol

from .desktop_bridge import TradingViewDesktopCli
from .desktop_chart_lock import DEFAULT_CHART_LOCK_PATH, desktop_chart_lock
from .models import Candle, ChartContext, DataSource, SourceState
from .providers import ChartContextProvider, DataSourceUnavailableError, normalize_timeframe

# Bridge resolution codes for each supported interval (TradingView's own naming).
RESOLUTION_BY_INTERVAL = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "1D": "1D",
    "1W": "1W",
    "M": "1M",
}

CHART_COMMAND_TIMEOUT_SECONDS = 30.0
# A read waits this long for another process's chart read to finish before it reports the chart as busy.
CHART_LOCK_TIMEOUT_SECONDS = 45.0

DESKTOP_CANDLE_WARNING = "Candles were read from the open TradingView Desktop chart, not the official MCP."


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ChartCli(Protocol):
    async def run(self, *args: str) -> object:
        ...


def _reason(error: BaseException) -> str:
    return str(error) if isinstance(error, DataSourceUnavailableError) else "unexpected error"


def _require_success(payload: object, action: str) -> dict:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise DataSourceUnavailableError(f"TradingView Desktop did not {action}.")
    return payload


class DesktopChartCandleProvider:
    """Reads candles from the open TradingView Desktop chart and restores the chart afterwards."""

    def __init__(
        self,
        cli: ChartCli,
        *,
        bar_count: int = 300,
        cache_for: timedelta = timedelta(seconds=120),
        clock: Callable[[], datetime] = _utc_now,
        settle_seconds: float = 1.5,
        poll_attempts: int = 8,
        sleep: Callable[[float], object] = asyncio.sleep,
        chart_lock_path: Optional[Path] = None,
    ) -> None:
        if bar_count < 2:
            raise ValueError("bar_count must be at least 2.")
        self._cli = cli
        self._bar_count = bar_count
        self._cache_for = cache_for
        self._clock = clock
        self._settle_seconds = settle_seconds
        self._poll_attempts = poll_attempts
        self._sleep = sleep
        self._chart_lock_path = chart_lock_path
        self._lock = asyncio.Lock()
        self._cache: dict[tuple[str, str], tuple[datetime, ChartContext]] = {}

    @classmethod
    def from_environment(cls, *, chart_lock_path: Optional[Path] = DEFAULT_CHART_LOCK_PATH) -> "DesktopChartCandleProvider":
        # Switching a chart symbol can take longer than a watchlist read, so chart commands get more time.
        # The lock is shared with the scheduled data jobs, which read the same chart in another process.
        return cls(
            TradingViewDesktopCli.from_environment(timeout_seconds=CHART_COMMAND_TIMEOUT_SECONDS),
            chart_lock_path=chart_lock_path,
        )

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        interval = normalize_timeframe(timeframe)
        resolution = RESOLUTION_BY_INTERVAL[interval]
        key = (symbol.strip().upper(), interval)
        cached = self._fresh_cached(key)
        if cached is not None:
            return cached
        async with self._lock:
            cached = self._fresh_cached(key)
            if cached is not None:
                return cached
            context = await self._read_chart(symbol, interval, resolution)
            self._cache[key] = (self._clock() + self._cache_for, context)
            return context

    def _exclusive_chart(self):
        """Hold the cross-process chart lock when one is configured; otherwise take no lock."""
        if self._chart_lock_path is None:
            return _NoChartLock()
        return desktop_chart_lock(self._chart_lock_path, timeout=CHART_LOCK_TIMEOUT_SECONDS)

    def _fresh_cached(self, key: tuple[str, str]) -> ChartContext | None:
        entry = self._cache.get(key)
        if entry is not None and self._clock() < entry[0]:
            return entry[1]
        return None

    async def _read_chart(self, symbol: str, interval: str, resolution: str) -> ChartContext:
        async with self._exclusive_chart():
            original = await self._current_chart()
            try:
                if original["symbol"].upper() != symbol.upper():
                    _require_success(await self._cli.run("symbol", symbol), f"switch to {symbol}")
                if original["resolution"] != resolution:
                    _require_success(await self._cli.run("timeframe", resolution), f"switch to {resolution}")
                await self._wait_for_chart(symbol, resolution)
                payload = _require_success(await self._cli.run("ohlcv", "-n", str(self._bar_count)), "return bars")
                candles = _bars_to_candles(payload)
            finally:
                await self._restore(original)
        return ChartContext(
            symbol=symbol,
            timeframe=interval,
            source=DataSource.DESKTOP_BRIDGE,
            source_timestamp=candles[-1].timestamp,
            freshness_state=SourceState.READY,
            candles=candles,
            warnings=[DESKTOP_CANDLE_WARNING],
        )

    async def _current_chart(self) -> dict:
        payload = _require_success(await self._cli.run("state"), "report the open chart")
        symbol, resolution = payload.get("symbol"), payload.get("resolution")
        if not isinstance(symbol, str) or not isinstance(resolution, str):
            raise DataSourceUnavailableError("TradingView Desktop did not report the open chart.")
        return {"symbol": symbol, "resolution": resolution}

    async def _wait_for_chart(self, symbol: str, resolution: str) -> None:
        for _ in range(self._poll_attempts):
            current = await self._current_chart()
            if current["symbol"].upper() == symbol.upper() and current["resolution"] == resolution:
                await self._sleep(self._settle_seconds)
                return
            await self._sleep(1.0)
        raise DataSourceUnavailableError(f"TradingView Desktop did not load {symbol} at {resolution} in time.")

    async def _restore(self, original: dict) -> None:
        """Put back the chart the user had open. A failure here is reported, never hidden."""
        current = await self._current_chart()
        if current["symbol"].upper() != original["symbol"].upper():
            _require_success(await self._cli.run("symbol", original["symbol"]), "restore the chart symbol")
        if current["resolution"] != original["resolution"]:
            _require_success(await self._cli.run("timeframe", original["resolution"]), "restore the chart interval")


class _NoChartLock:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc_info: object) -> None:
        return None


def _bars_to_candles(payload: dict) -> list[Candle]:
    bars = payload.get("bars")
    if not isinstance(bars, list):
        raise DataSourceUnavailableError("TradingView Desktop returned no bars for the chart.")
    candles: list[Candle] = []
    for bar in bars:
        try:
            candles.append(
                Candle(
                    timestamp=datetime.fromtimestamp(int(bar["time"]), tz=timezone.utc),
                    open=float(bar["open"]),
                    high=float(bar["high"]),
                    low=float(bar["low"]),
                    close=float(bar["close"]),
                    volume=float(bar["volume"]) if bar.get("volume") is not None else None,
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    if len(candles) < 2:
        raise DataSourceUnavailableError("TradingView Desktop returned fewer than two candles for the chart.")
    return sorted(candles, key=lambda candle: candle.timestamp)


class FallbackChartProvider:
    """Official MCP first; the Desktop chart only when the MCP read fails."""

    def __init__(self, primary: ChartContextProvider, fallback: ChartContextProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        try:
            return await self._primary.get_chart_context(symbol, timeframe)
        except Exception as primary_error:  # noqa: BLE001 - any MCP failure triggers the Desktop fallback
            primary_reason = _reason(primary_error)
        try:
            context = await self._fallback.get_chart_context(symbol, timeframe)
        except Exception as fallback_error:  # noqa: BLE001 - reported to the caller with both reasons
            raise DataSourceUnavailableError(
                f"{primary_reason} Desktop fallback: {_reason(fallback_error)}"
            ) from fallback_error
        note = f"Official TradingView MCP was unavailable ({primary_reason}); candles were read from TradingView Desktop."
        return context.model_copy(update={"warnings": [note, *context.warnings]})
