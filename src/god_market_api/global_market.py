"""Global-market context providers for the local dashboard."""

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol, Sequence

from .desktop_bridge import DesktopWatchlistQuoteSnapshot, TradingViewDesktopWatchlistReader
from .models import (
    ChartContext,
    DataSource,
    DesktopFallbackState,
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


# Read-only snapshot captured from PS_Global_Indices on 2026-10-07. It is not
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
            WatchlistInstrumentDefinition("CBOEFTSE:RUT", "Russell 2000"),
            WatchlistInstrumentDefinition("TVC:DXY", "US Dollar Currency Index"),
            WatchlistInstrumentDefinition("TVC:VIX", "CBOE Volatility Index"),
        ),
    ),
    WatchlistGroupDefinition(
        name="EUROPE",
        instruments=(
            WatchlistInstrumentDefinition("XETR:DAX", "DAX"),
            WatchlistInstrumentDefinition("TVC:CAC40", "CAC 40"),
            WatchlistInstrumentDefinition("FTSE:UKX", "FTSE 100"),
        ),
    ),
    WatchlistGroupDefinition(
        name="ASIA PACIFIC",
        instruments=(
            WatchlistInstrumentDefinition("NSEIX:NIFTY1!", "GIFT Nifty 50 Futures"),
            WatchlistInstrumentDefinition("TVC:HSI", "Hang Seng Index"),
            WatchlistInstrumentDefinition("TVC:NI225", "Nikkei 225"),
            WatchlistInstrumentDefinition("TVC:STI", "Straits Times Index"),
            WatchlistInstrumentDefinition("KRX:KOSPI", "KOSPI Composite Index"),
            WatchlistInstrumentDefinition("ASX:XJO", "S&P/ASX 200"),
            WatchlistInstrumentDefinition("IDX:COMPOSITE", "IDX Composite"),
            WatchlistInstrumentDefinition("SET:SET", "SET Index"),
            WatchlistInstrumentDefinition("TWSE:TAIEX", "Taiwan Weighted Index"),
            WatchlistInstrumentDefinition("SSE:000300", "CSI 300 Index"),
        ),
    ),
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


def _desktop_fallback_state(groups: Sequence[GlobalMarketGroup]) -> DesktopFallbackState:
    priced = [item for group in groups for item in group.instruments if item.last_price is not None]
    desktop_count = sum(item.source is DataSource.DESKTOP_BRIDGE for item in priced)
    if desktop_count == 0:
        return DesktopFallbackState.NONE
    return DesktopFallbackState.FULL if desktop_count == len(priced) else DesktopFallbackState.PARTIAL


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
            desktop_fallback=_desktop_fallback_state(ordered_groups),
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


async def _read_desktop_quotes(
    reader: TradingViewDesktopWatchlistReader, expected_symbols: Sequence[str]
) -> DesktopWatchlistQuoteSnapshot | DataSourceUnavailableError:
    try:
        return await reader.get_quotes(expected_symbols)
    except DataSourceUnavailableError as error:
        return error


@dataclass
class _OfficialAttempts:
    """Per-refresh limits that hand remaining items to the Desktop fallback quickly."""

    deadline: float
    failure_limit: int
    consecutive_failures: int = 0
    stopped_reason: str | None = None

    def remaining(self) -> float:
        return self.deadline - asyncio.get_running_loop().time()

    def stop(self, reason: str) -> None:
        if self.stopped_reason is None:
            self.stopped_reason = reason

    def record_success(self) -> None:
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failure_limit:
            self.stop(
                f"Skipped after {self.failure_limit} consecutive official TradingView MCP failures in this refresh."
            )


class GlobalMarketLiveSnapshotProvider:
    """Read official-MCP OHLCV for the approved watchlist without trading actions."""

    def __init__(
        self,
        provider: ChartContextProvider,
        *,
        desktop_watchlist_reader: TradingViewDesktopWatchlistReader | None = None,
        watchlist_groups: Sequence[WatchlistGroupDefinition] = RECORDED_WATCHLIST_GROUPS,
        clock: Callable[[], datetime] = _utc_now,
        max_provider_concurrency: int = 6,
        cache_for: timedelta = timedelta(seconds=60),
        retry_attempts: int = 1,
        retry_delay_seconds: float = 1.0,
        official_time_budget_seconds: float = 20.0,
        official_failure_limit: int = 3,
    ) -> None:
        if max_provider_concurrency < 1:
            raise ValueError("max_provider_concurrency must be at least 1.")
        if retry_attempts < 0 or retry_delay_seconds < 0:
            raise ValueError("retry_attempts and retry_delay_seconds must not be negative.")
        if official_time_budget_seconds <= 0 or official_failure_limit < 1:
            raise ValueError("official_time_budget_seconds and official_failure_limit must be positive.")
        self._retry_attempts = retry_attempts
        self._retry_delay_seconds = retry_delay_seconds
        self._official_time_budget_seconds = official_time_budget_seconds
        self._official_failure_limit = official_failure_limit
        if cache_for < timedelta(0):
            raise ValueError("cache_for must not be negative.")
        self._provider = provider
        self._desktop_watchlist_reader = desktop_watchlist_reader
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
            expected_symbols = [item.symbol for group in self._watchlist_groups for item in group.instruments]
            desktop_task = (
                asyncio.create_task(_read_desktop_quotes(self._desktop_watchlist_reader, expected_symbols))
                if self._desktop_watchlist_reader is not None
                else None
            )
            attempts = _OfficialAttempts(
                deadline=asyncio.get_running_loop().time() + self._official_time_budget_seconds,
                failure_limit=self._official_failure_limit,
            )
            batch_session = getattr(self._provider, "batch_session", None)
            async with batch_session() if batch_session is not None else nullcontext() as official_ready:
                if official_ready is False and desktop_task is not None:
                    if isinstance(await desktop_task, DesktopWatchlistQuoteSnapshot):
                        attempts.stop("Official TradingView MCP session could not be opened for this refresh.")
                groups = await asyncio.gather(
                    *(self._read_group(group, timeframe, attempts) for group in self._watchlist_groups)
                )
            warnings = [
                "Official TradingView MCP is the primary source for available price evidence.",
                "Watchlist groups use the read-only PS_Global_Indices snapshot recorded on 2026-10-07.",
            ]
            if attempts.stopped_reason:
                warnings.append(f"Official TradingView MCP requests stopped early: {attempts.stopped_reason}")
            unavailable_count = sum(
                item.direction is MarketDirection.UNAVAILABLE
                for group in groups
                for item in group.instruments
            )
            desktop_result = None
            if desktop_task is not None:
                if unavailable_count:
                    desktop_result = await desktop_task
                else:
                    desktop_task.cancel()
                    await asyncio.gather(desktop_task, return_exceptions=True)
            if unavailable_count and isinstance(desktop_result, DataSourceUnavailableError):
                warnings.append(f"Desktop fallback was unavailable: {desktop_result}")
            elif unavailable_count and isinstance(desktop_result, DesktopWatchlistQuoteSnapshot):
                groups = self._apply_desktop_watchlist_quotes(groups, desktop_result)
                fallback_count = sum(
                    item.source is DataSource.DESKTOP_BRIDGE
                    for group in groups
                    for item in group.instruments
                )
                if fallback_count:
                    warnings.append(
                        f"Desktop watchlist quotes supplied fallback evidence for {fallback_count} item(s); "
                        "the source timestamp is the local read time."
                    )
                missing_rows = sum(
                    item.direction is MarketDirection.UNAVAILABLE and item.source is not DataSource.DESKTOP_BRIDGE
                    for group in groups
                    for item in group.instruments
                )
                if missing_rows:
                    warnings.append(
                        f"{missing_rows} unavailable item(s) had no visible row in the Desktop watchlist; "
                        "scroll or resize the watchlist panel so every row is visible."
                    )
            snapshot = self._service.build_snapshot(
                timeframe=timeframe,
                groups=groups,
                warnings=warnings,
            )
            self._snapshot_cache[timeframe] = (self._clock() + self._cache_for, snapshot)
            return snapshot

    async def _read_group(
        self, definition: WatchlistGroupDefinition, timeframe: str, attempts: "_OfficialAttempts"
    ) -> GlobalMarketGroup:
        instruments = await asyncio.gather(
            *(self._read_instrument(item, timeframe, attempts) for item in definition.instruments)
        )
        return GlobalMarketGroup(name=definition.name, instruments=list(instruments))

    async def _read_instrument(
        self, definition: WatchlistInstrumentDefinition, timeframe: str, attempts: "_OfficialAttempts"
    ) -> GlobalMarketInstrument:
        budget_reason = (
            f"Official TradingView MCP did not respond within the {self._official_time_budget_seconds:g} s "
            "refresh budget."
        )
        for attempt in range(self._retry_attempts + 1):
            if attempts.stopped_reason:
                return self._unavailable(definition, attempts.stopped_reason)
            remaining = attempts.remaining()
            if remaining <= 0:
                attempts.stop(budget_reason)
                return self._unavailable(definition, budget_reason)
            try:
                context = await asyncio.wait_for(self._fetch_price_context(definition.symbol, timeframe), remaining)
                break
            except TimeoutError:
                attempts.stop(budget_reason)
                return self._unavailable(definition, budget_reason)
            except Exception as error:
                if attempt < self._retry_attempts:
                    await asyncio.sleep(min(self._retry_delay_seconds, max(attempts.remaining(), 0)))
                    continue
                attempts.record_failure()
                if isinstance(error, DataSourceUnavailableError):
                    return self._unavailable(definition, str(error))
                return self._unavailable(
                    definition, "Official TradingView MCP could not provide current price evidence for this item."
                )
        attempts.record_success()

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

    async def _fetch_price_context(self, symbol: str, timeframe: str) -> ChartContext:
        async with self._semaphore:
            get_price_context = getattr(self._provider, "get_price_context", None)
            if get_price_context is not None:
                return await get_price_context(symbol, timeframe, candle_count=2)
            return await self._provider.get_chart_context(symbol, timeframe)

    def _apply_desktop_watchlist_quotes(
        self,
        groups: Sequence[GlobalMarketGroup],
        desktop_snapshot: DesktopWatchlistQuoteSnapshot,
    ) -> list[GlobalMarketGroup]:
        fallback_warning = (
            "Desktop-assisted fallback: price/change came from the visible TradingView watchlist row; "
            "the bridge does not provide a per-quote market timestamp or historical candles."
        )
        updated_groups: list[GlobalMarketGroup] = []
        for group in groups:
            instruments: list[GlobalMarketInstrument] = []
            for instrument in group.instruments:
                quote = desktop_snapshot.quotes.get(instrument.symbol.upper())
                if instrument.direction is not MarketDirection.UNAVAILABLE or quote is None or quote.last_price is None:
                    instruments.append(instrument)
                    continue
                official_warning = f"Official MCP evidence was unavailable: {instrument.unavailable_reason}"
                fallback_warnings = [official_warning, fallback_warning]
                if quote.change_percent is None:
                    instruments.append(
                        instrument.model_copy(
                            update={
                                "last_price": quote.last_price,
                                "source": DataSource.DESKTOP_BRIDGE,
                                "source_timestamp": desktop_snapshot.observed_at,
                                "freshness_state": SourceState.READY,
                                "warnings": fallback_warnings,
                                "unavailable_reason": (
                                    "Desktop quote is available, but the watchlist row has no daily change percentage; "
                                    "this item remains excluded from breadth."
                                ),
                            }
                        )
                    )
                    continue
                direction = (
                    MarketDirection.ADVANCING
                    if quote.change_percent > 0
                    else MarketDirection.DECLINING
                    if quote.change_percent < 0
                    else MarketDirection.UNCHANGED
                )
                instruments.append(
                    instrument.model_copy(
                        update={
                            "last_price": quote.last_price,
                            "change_percent": quote.change_percent,
                            "direction": direction,
                            "source": DataSource.DESKTOP_BRIDGE,
                            "source_timestamp": desktop_snapshot.observed_at,
                            "freshness_state": SourceState.READY,
                            "warnings": fallback_warnings,
                            "unavailable_reason": None,
                        }
                    )
                )
            updated_groups.append(group.model_copy(update={"instruments": instruments}))
        return updated_groups

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
