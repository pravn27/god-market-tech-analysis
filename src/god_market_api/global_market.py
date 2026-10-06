"""Global-market context providers for the local dashboard."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol, Sequence

from .models import (
    DataSource,
    GlobalMarketBreadth,
    GlobalMarketCompleteness,
    GlobalMarketGroup,
    GlobalMarketInstrument,
    GlobalMarketSnapshot,
    MarketDirection,
    SourceState,
)
from .providers import ChartContextProvider, DataSourceUnavailableError


WATCHLIST_NAME = "PS_Global_Indices"


@dataclass(frozen=True)
class WatchlistInstrumentDefinition:
    """A read-only entry from the approved Desktop watchlist snapshot."""

    symbol: str
    display_name: str


@dataclass(frozen=True)
class WatchlistGroupDefinition:
    """An ordered section from the approved Desktop watchlist snapshot."""

    name: str
    instruments: tuple[WatchlistInstrumentDefinition, ...] = ()


# Read-only snapshot captured from PS_Global_Indices on 2026-10-06. It is not
# a replacement universe and must not be changed without the separate coverage
# dry-run and the user's explicit confirmation.
RECORDED_WATCHLIST_GROUPS = (
    WatchlistGroupDefinition(
        name="USA",
        instruments=(
            WatchlistInstrumentDefinition("TVC:DJI", "Dow Jones Industrial Average"),
            WatchlistInstrumentDefinition("DJCFD:DJT", "Dow Jones Transportation Average"),
            WatchlistInstrumentDefinition("NASDAQ:NDX", "Nasdaq 100"),
            WatchlistInstrumentDefinition("CBOE:MAGS", "Magnificent 7 Index"),
            WatchlistInstrumentDefinition("NASDAQ:IXIC", "Nasdaq Composite"),
            WatchlistInstrumentDefinition("VANTAGE:USDINR", "USD / INR"),
            WatchlistInstrumentDefinition("TVC:SPX", "S&P 500"),
            WatchlistInstrumentDefinition("BLACKBULL:DJ30.F", "Dow Jones 30 Futures"),
            WatchlistInstrumentDefinition("BLACKBULL:US30", "US Wall Street 30"),
            WatchlistInstrumentDefinition("TVC:NYA", "NYSE Composite"),
            WatchlistInstrumentDefinition("TVC:DXY", "US Dollar Currency Index"),
            WatchlistInstrumentDefinition("TVC:VIX", "CBOE Volatility Index"),
        ),
    ),
    WatchlistGroupDefinition(name="EUROPE"),
    WatchlistGroupDefinition(name="ASIA PACIFIC"),
    WatchlistGroupDefinition(
        name="INDIA ADRS",
        instruments=(
            WatchlistInstrumentDefinition("NYSE:INFY", "Infosys ADR"),
            WatchlistInstrumentDefinition("NYSE:WIT", "Wipro ADR"),
            WatchlistInstrumentDefinition("NYSE:IBN", "ICICI Bank ADR"),
            WatchlistInstrumentDefinition("NYSE:HDB", "HDFC Bank ADR"),
        ),
    ),
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GlobalMarketSnapshotProvider(Protocol):
    """Boundary for a read-only global-market snapshot source."""

    async def get_snapshot(self, timeframe: str) -> GlobalMarketSnapshot:
        ...


def calculate_breadth(groups: Sequence[GlobalMarketGroup]) -> GlobalMarketBreadth:
    """Count only explicit direction evidence; retain unavailable evidence separately."""
    counts = {
        MarketDirection.ADVANCING: 0,
        MarketDirection.DECLINING: 0,
        MarketDirection.UNCHANGED: 0,
        MarketDirection.UNAVAILABLE: 0,
    }
    for group in groups:
        for instrument in group.instruments:
            counts[instrument.direction] += 1
    return GlobalMarketBreadth(
        advancing=counts[MarketDirection.ADVANCING],
        declining=counts[MarketDirection.DECLINING],
        unchanged=counts[MarketDirection.UNCHANGED],
        unavailable=counts[MarketDirection.UNAVAILABLE],
    )


class GlobalMarketSnapshotService:
    """Build an ordered, evidence-only dashboard response from a supplied universe."""

    def __init__(
        self,
        *,
        watchlist_name: str = WATCHLIST_NAME,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._watchlist_name = watchlist_name
        self._clock = clock

    def build_snapshot(
        self,
        *,
        timeframe: str,
        groups: Sequence[GlobalMarketGroup],
        warnings: Sequence[str] = (),
    ) -> GlobalMarketSnapshot:
        """Build completeness and breadth without interpreting a trading direction."""
        ordered_groups = list(groups)
        breadth = calculate_breadth(ordered_groups)
        available_count = breadth.advancing + breadth.declining + breadth.unchanged
        completeness = (
            GlobalMarketCompleteness.UNAVAILABLE
            if available_count == 0
            else GlobalMarketCompleteness.PARTIAL
            if breadth.unavailable
            else GlobalMarketCompleteness.COMPLETE
        )
        combined_warnings = list(warnings)
        if breadth.unavailable:
            combined_warnings.append(
                "Unavailable items are excluded from advancing, declining, and unchanged breadth counts."
            )
        return GlobalMarketSnapshot(
            watchlist_name=self._watchlist_name,
            read_at=self._clock(),
            timeframe=timeframe,
            completeness=completeness,
            groups=ordered_groups,
            breadth=breadth,
            warnings=combined_warnings,
        )


class FixtureGlobalMarketSnapshotProvider:
    """Explicitly non-live evidence for the first dashboard/API vertical slice."""

    def __init__(self, *, clock: Callable[[], datetime] = _utc_now) -> None:
        self._clock = clock
        self._service = GlobalMarketSnapshotService(clock=clock)

    async def get_snapshot(self, timeframe: str) -> GlobalMarketSnapshot:
        observed_at = self._clock()
        return self._service.build_snapshot(
            timeframe=timeframe,
            groups=[
                GlobalMarketGroup(
                    name="USA",
                    instruments=[
                        self._available("TVC:DJI", "Dow Jones Industrial Average", 100.0, 0.45, observed_at),
                        self._available("NASDAQ:NDX", "Nasdaq 100", 200.0, 0.31, observed_at),
                        self._available("TVC:SPX", "S&P 500", 150.0, -0.18, observed_at),
                    ],
                ),
                GlobalMarketGroup(name="EUROPE"),
                GlobalMarketGroup(name="ASIA PACIFIC"),
                GlobalMarketGroup(
                    name="INDIA ADRS",
                    instruments=[
                        GlobalMarketInstrument(
                            symbol="NYSE:INFY",
                            display_name="Infosys ADR",
                            direction=MarketDirection.UNAVAILABLE,
                            source=DataSource.FIXTURE,
                            freshness_state=SourceState.UNAVAILABLE,
                            unavailable_reason="Fixture does not include a current value for this item.",
                        )
                    ],
                ),
            ],
            warnings=[
                "Fixture data only: values are illustrative and no live TradingView market-data request was made."
            ],
        )

    @staticmethod
    def _available(
        symbol: str,
        display_name: str,
        last_price: float,
        change_percent: float,
        observed_at: datetime,
    ) -> GlobalMarketInstrument:
        return GlobalMarketInstrument(
            symbol=symbol,
            display_name=display_name,
            last_price=last_price,
            change_percent=change_percent,
            direction=(
                MarketDirection.ADVANCING if change_percent > 0 else MarketDirection.DECLINING
            ),
            source=DataSource.FIXTURE,
            source_timestamp=observed_at,
            freshness_state=SourceState.READY,
        )


class GlobalMarketLiveSnapshotProvider:
    """Read official-MCP OHLCV for the approved watchlist without trading actions."""

    def __init__(
        self,
        provider: ChartContextProvider,
        *,
        watchlist_groups: Sequence[WatchlistGroupDefinition] = RECORDED_WATCHLIST_GROUPS,
        clock: Callable[[], datetime] = _utc_now,
        max_provider_concurrency: int = 6,
        cache_for: timedelta = timedelta(seconds=60),
    ) -> None:
        if max_provider_concurrency < 1:
            raise ValueError("max_provider_concurrency must be at least 1.")
        if cache_for < timedelta(0):
            raise ValueError("cache_for must not be negative.")
        self._provider = provider
        self._watchlist_groups = tuple(watchlist_groups)
        self._clock = clock
        self._service = GlobalMarketSnapshotService(clock=clock)
        self._semaphore = asyncio.Semaphore(max_provider_concurrency)
        self._cache_for = cache_for
        self._snapshot_cache: dict[str, tuple[datetime, GlobalMarketSnapshot]] = {}
        self._snapshot_lock = asyncio.Lock()

    async def get_snapshot(self, timeframe: str) -> GlobalMarketSnapshot:
        """Read each approved item with bounded concurrency and preserve every failure."""
        cached = self._cached_snapshot(timeframe)
        if cached is not None:
            return cached
        async with self._snapshot_lock:
            cached = self._cached_snapshot(timeframe)
            if cached is not None:
                return cached
            groups = await asyncio.gather(
                *(self._read_group(group, timeframe) for group in self._watchlist_groups)
            )
            snapshot = self._service.build_snapshot(
                timeframe=timeframe,
                groups=groups,
                warnings=[
                    "Official TradingView MCP is the primary source for available price evidence.",
                    "Watchlist groups use the read-only PS_Global_Indices snapshot recorded on 2026-10-06.",
                ],
            )
            self._snapshot_cache[timeframe] = (self._clock() + self._cache_for, snapshot)
            return snapshot

    async def _read_group(
        self, definition: WatchlistGroupDefinition, timeframe: str
    ) -> GlobalMarketGroup:
        instruments = await asyncio.gather(
            *(self._read_instrument(item, timeframe) for item in definition.instruments)
        )
        return GlobalMarketGroup(name=definition.name, instruments=list(instruments))

    async def _read_instrument(
        self, definition: WatchlistInstrumentDefinition, timeframe: str
    ) -> GlobalMarketInstrument:
        try:
            async with self._semaphore:
                get_price_context = getattr(self._provider, "get_price_context", None)
                if get_price_context is not None:
                    context = await get_price_context(definition.symbol, timeframe, candle_count=2)
                else:
                    context = await self._provider.get_chart_context(definition.symbol, timeframe)
        except DataSourceUnavailableError as error:
            return self._unavailable(definition, str(error))
        except Exception:
            return self._unavailable(
                definition, "Official TradingView MCP could not provide current price evidence for this item."
            )

        candles = sorted(context.candles, key=lambda candle: candle.timestamp)
        if len(candles) < 2:
            return self._unavailable(
                definition, "Official TradingView MCP returned fewer than two candles for this item."
            )
        previous, current = candles[-2:]
        if previous.close == 0:
            return self._unavailable(
                definition, "Official TradingView MCP returned a zero previous close for this item."
            )
        change_percent = ((current.close - previous.close) / previous.close) * 100
        direction = (
            MarketDirection.ADVANCING
            if current.close > previous.close
            else MarketDirection.DECLINING
            if current.close < previous.close
            else MarketDirection.UNCHANGED
        )
        return GlobalMarketInstrument(
            symbol=definition.symbol,
            display_name=definition.display_name,
            last_price=current.close,
            change_percent=change_percent,
            direction=direction,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=context.source_timestamp,
            freshness_state=context.freshness_state,
            warnings=context.warnings,
        )

    @staticmethod
    def _unavailable(
        definition: WatchlistInstrumentDefinition, unavailable_reason: str
    ) -> GlobalMarketInstrument:
        return GlobalMarketInstrument(
            symbol=definition.symbol,
            display_name=definition.display_name,
            direction=MarketDirection.UNAVAILABLE,
            source=DataSource.OFFICIAL_MCP,
            freshness_state=SourceState.UNAVAILABLE,
            unavailable_reason=unavailable_reason,
        )

    def _cached_snapshot(self, timeframe: str) -> GlobalMarketSnapshot | None:
        cached = self._snapshot_cache.get(timeframe)
        if cached is None:
            return None
        expires_at, snapshot = cached
        return snapshot if self._clock() <= expires_at else None
