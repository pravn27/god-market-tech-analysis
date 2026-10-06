"""Application use case for assembling source-attributed MTF context."""

import asyncio
from datetime import datetime, timezone
from typing import Callable, Iterable

from .models import (
    AnalysisTimeframe,
    DataSource,
    MultiTimeframeCompleteness,
    MultiTimeframeContext,
    TimeframeContextResult,
    default_mtf_timeframes,
)
from .mtf_cache import LocalContextCache
from .providers import ChartContextProvider, DataSourceUnavailableError


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MultiTimeframeContextOrchestrator:
    """Coordinate unique timeframe context without making trading decisions."""

    def __init__(
        self,
        provider: ChartContextProvider,
        *,
        source: DataSource = DataSource.OFFICIAL_MCP,
        cache: LocalContextCache | None = None,
        timeframes: Iterable[AnalysisTimeframe] | None = None,
        clock: Callable[[], datetime] = _utc_now,
        max_provider_concurrency: int = 3,
    ) -> None:
        if max_provider_concurrency < 1:
            raise ValueError("max_provider_concurrency must be at least 1.")
        self._provider = provider
        self._source = source
        self._cache = cache or LocalContextCache(clock=clock)
        self._timeframes = self._unique_timeframes(timeframes or default_mtf_timeframes())
        self._clock = clock
        self._provider_semaphore = asyncio.Semaphore(max_provider_concurrency)
        self._inflight: dict[tuple[str, AnalysisTimeframe], asyncio.Task[TimeframeContextResult]] = {}

    async def get_context(
        self,
        symbol: str,
        *,
        timeframes: Iterable[AnalysisTimeframe] | None = None,
        force_refresh: bool = False,
    ) -> MultiTimeframeContext:
        """Return complete, partial, or unavailable source evidence for one symbol."""
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("A symbol is required.")

        selected_timeframes = self._unique_timeframes(timeframes or self._timeframes)
        results = await asyncio.gather(
            *(
                self._resolve_timeframe(normalized_symbol, timeframe, force_refresh=force_refresh)
                for timeframe in selected_timeframes
            )
        )
        contexts = {result.timeframe: result for result in results}
        successful_count = sum(result.context is not None for result in results)
        completeness = (
            MultiTimeframeCompleteness.COMPLETE
            if successful_count == len(results)
            else MultiTimeframeCompleteness.PARTIAL
            if successful_count
            else MultiTimeframeCompleteness.UNAVAILABLE
        )
        warnings = [
            f"{result.timeframe.value}: {result.unavailable_reason}"
            for result in results
            if result.unavailable_reason
        ]
        return MultiTimeframeContext(
            symbol=normalized_symbol,
            requested_at=self._clock(),
            completeness=completeness,
            contexts=contexts,
            warnings=warnings,
        )

    async def _resolve_timeframe(
        self, symbol: str, timeframe: AnalysisTimeframe, *, force_refresh: bool
    ) -> TimeframeContextResult:
        if not force_refresh:
            cached = self._cache.get(self._source, symbol, timeframe)
            if cached.context is not None:
                return TimeframeContextResult(timeframe=timeframe, context=cached.context)

        key = (symbol, timeframe)
        in_flight = self._inflight.get(key)
        if in_flight is None:
            in_flight = asyncio.create_task(self._fetch_from_provider(symbol, timeframe))
            self._inflight[key] = in_flight
            in_flight.add_done_callback(lambda completed: self._remove_inflight(key, completed))
        return await asyncio.shield(in_flight)

    async def _fetch_from_provider(
        self, symbol: str, timeframe: AnalysisTimeframe
    ) -> TimeframeContextResult:
        try:
            async with self._provider_semaphore:
                context = await self._provider.get_chart_context(symbol, timeframe.value)
        except DataSourceUnavailableError as error:
            return TimeframeContextResult(timeframe=timeframe, unavailable_reason=str(error))
        except Exception:
            return TimeframeContextResult(
                timeframe=timeframe,
                unavailable_reason="The market-data source could not provide this timeframe.",
            )

        self._cache.put(timeframe, context)
        return TimeframeContextResult(timeframe=timeframe, context=context)

    def _remove_inflight(
        self, key: tuple[str, AnalysisTimeframe], completed: asyncio.Task[TimeframeContextResult]
    ) -> None:
        if self._inflight.get(key) is completed:
            self._inflight.pop(key, None)

    @staticmethod
    def _unique_timeframes(timeframes: Iterable[AnalysisTimeframe]) -> tuple[AnalysisTimeframe, ...]:
        unique = tuple(dict.fromkeys(timeframes))
        if not unique:
            raise ValueError("At least one timeframe is required.")
        return unique
