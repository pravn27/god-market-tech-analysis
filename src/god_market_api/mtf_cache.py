"""Process-local cache for read-only multi-timeframe chart context."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .models import AnalysisTimeframe, ChartContext, DataSource, SourceState
from .mtf_policy import CacheFreshness, FreshnessPolicy, classify_freshness


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CacheLookup:
    """A cache outcome that lets the orchestrator decide whether to refresh."""

    freshness: CacheFreshness
    context: ChartContext | None = None


@dataclass(frozen=True)
class _CacheKey:
    source: DataSource
    symbol: str
    timeframe: AnalysisTimeframe


class LocalContextCache:
    """In-memory cache keyed by source, normalized symbol, and timeframe."""

    def __init__(
        self,
        *,
        policy: FreshnessPolicy | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._policy = policy or FreshnessPolicy.defaults()
        self._clock = clock
        self._entries: dict[_CacheKey, ChartContext] = {}

    def put(self, timeframe: AnalysisTimeframe, context: ChartContext) -> None:
        """Store provider context; credentials and raw source payloads are never retained."""
        self._entries[self._key(context.source, context.symbol, timeframe)] = context

    def get(
        self,
        source: DataSource,
        symbol: str,
        timeframe: AnalysisTimeframe,
        *,
        now: datetime | None = None,
    ) -> CacheLookup:
        """Return usable cached context, or a typed state that requires a refresh."""
        context = self._entries.get(self._key(source, symbol, timeframe))
        if context is None:
            return CacheLookup(freshness=CacheFreshness.UNAVAILABLE)

        freshness = classify_freshness(
            timeframe,
            context.source_timestamp,
            now=now or self._clock(),
            policy=self._policy,
        )
        if freshness is CacheFreshness.EXPIRED:
            return CacheLookup(freshness=freshness)
        if freshness is CacheFreshness.STALE:
            return CacheLookup(
                freshness=freshness,
                context=context.model_copy(update={"freshness_state": SourceState.STALE}),
            )
        return CacheLookup(
            freshness=freshness,
            context=context.model_copy(update={"freshness_state": SourceState.READY}),
        )

    @staticmethod
    def _key(source: DataSource, symbol: str, timeframe: AnalysisTimeframe) -> _CacheKey:
        return _CacheKey(source=source, symbol=symbol.strip().upper(), timeframe=timeframe)
