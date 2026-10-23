"""Use case: PAPA + SMM multi-timeframe checklist for one watchlist instrument."""

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Protocol

from .global_market import WatchlistUnavailableError
from .models import (
    AnalysisTimeframe,
    Bias,
    ChecklistCell,
    MtfChecklistRow,
    MtfDecisions,
    MtfInstrument,
    MtfInstrumentCatalog,
    MtfInstrumentSection,
    MtfTimeframeStatus,
    MultiTimeframeAnalysis,
    MultiTimeframeCompleteness,
    SourceState,
    TimeframeContextResult,
    default_mtf_timeframes,
)
from .mtf_checklist import CHECKLIST_ROWS, ChecklistThresholds, TimeframeEvaluation, evaluate_timeframe
from .mtf_orchestrator import MultiTimeframeContextOrchestrator
from .mtf_screens import DISCLAIMER, evaluate_screens
from .providers import DataSourceUnavailableError
from .watchlist_source import check_matches_recorded, parse_bridge_sequence, symbols_of

SNAPSHOT_PATH = Path(__file__).parent / "data" / "mtf_watchlist.json"

STALE_REASON = "Cached data is stale and could not be refreshed."

IST = timezone(timedelta(hours=5, minutes=30))

# Session close in IST per exchange prefix. Exchanges not listed trade around the clock
# (CFD brokers such as PEPPERSTONE, and TVC / CAPITALCOM): their candles end with their period.
# MCX is taken as 23:30; its 23:55 schedule during US daylight-saving time is not modelled.
SESSION_CLOSE_BY_EXCHANGE: dict[str, time] = {"NSE": time(15, 30), "MCX": time(23, 30)}

_PERIODS = {
    AnalysisTimeframe.WEEKLY: timedelta(weeks=1),
    AnalysisTimeframe.DAILY: timedelta(days=1),
    AnalysisTimeframe.FOUR_HOUR: timedelta(hours=4),
    AnalysisTimeframe.ONE_HOUR: timedelta(hours=1),
    AnalysisTimeframe.FIFTEEN_MINUTE: timedelta(minutes=15),
}


class UnknownInstrumentError(ValueError):
    """The symbol is not part of the recorded watchlist snapshot."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def display_name(symbol: str) -> str:
    """Ticker part of an exchange-prefixed symbol, e.g. 'PEPPERSTONE:NATGAS' -> 'NATGAS'."""
    return symbol.split(":")[-1]


def load_instrument_catalog(path: Path = SNAPSHOT_PATH) -> MtfInstrumentCatalog:
    raw = json.loads(path.read_text())
    return MtfInstrumentCatalog(
        watchlist_name=raw["watchlist_name"],
        recorded_at=raw["recorded_at"],
        default_symbol=raw["default_symbol"],
        sections=[
            MtfInstrumentSection(
                name=section["name"],
                instruments=[MtfInstrument(symbol=s, display_name=display_name(s)) for s in section["symbols"]],
            )
            for section in raw["sections"]
        ],
    )


def exchange_of(symbol: str) -> str:
    """Exchange prefix of a symbol, e.g. 'MCX:GOLD1!' -> 'MCX'."""
    return symbol.split(":")[0].upper() if ":" in symbol else ""


def _session_close(day: date, close: time) -> datetime:
    return datetime.combine(day, close, IST)


def candle_closes_at(timeframe: AnalysisTimeframe, opened_at: datetime, exchange: str = "NSE") -> datetime:
    """When the latest candle stops changing, using the exchange's session. Holidays are not modelled."""
    close = SESSION_CLOSE_BY_EXCHANGE.get(exchange)
    opened = opened_at.astimezone(IST)
    if timeframe is AnalysisTimeframe.MONTHLY:
        if close is None:
            first = opened.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return (first + timedelta(days=32)).replace(day=1)
        next_month = (opened.replace(day=28) + timedelta(days=4)).replace(day=1).date()
        last_day = next_month - timedelta(days=1)
        while last_day.weekday() > 4:
            last_day -= timedelta(days=1)
        return _session_close(last_day, close)
    if close is None:
        return opened_at + _PERIODS[timeframe]
    if timeframe is AnalysisTimeframe.WEEKLY:
        return _session_close(opened.date() + timedelta(days=4 - opened.weekday()), close)
    if timeframe is AnalysisTimeframe.DAILY:
        return _session_close(opened.date(), close)
    return min(opened_at + _PERIODS[timeframe], _session_close(opened.date(), close))


def is_live_candle(timeframe: AnalysisTimeframe, opened_at: datetime, now: datetime, exchange: str = "NSE") -> bool:
    """Whether the latest candle can still change, i.e. its exchange session has not closed yet."""
    return now < candle_closes_at(timeframe, opened_at, exchange)


class MtfCatalogSource(Protocol):
    async def catalog(self) -> MtfInstrumentCatalog: ...


class DesktopWatchlistPayloadReader(Protocol):
    async def watchlist_payload(self) -> object: ...


CATALOG_ORIGIN_DESKTOP = "tradingview_desktop"
CATALOG_ORIGIN_SNAPSHOT = "recorded_snapshot"
UNSECTIONED_NAME = "WATCHLIST"


class DesktopMtfCatalogSource:
    """The MTF instrument list from the visible TradingView Desktop watchlist, used only while the MCP quota is over.

    While the official quota is available, the recorded snapshot is returned and the Desktop is not read.
    While it is used up, the visible watchlist is read (read-only: no watchlist or chart switching). It is
    accepted only if its rows match the recorded snapshot. Its order and section names come from the
    snapshot; visible symbols that the snapshot does not list go into a trailing ``WATCHLIST`` section.
    Any failure returns the snapshot. The result is cached for ``cache_for`` in either case.
    """

    def __init__(
        self,
        reader: DesktopWatchlistPayloadReader,
        snapshot: MtfInstrumentCatalog,
        *,
        quota_blocked: Callable[[], bool],
        clock: Callable[[], datetime] = _utc_now,
        cache_for: timedelta = timedelta(minutes=5),
    ) -> None:
        self._reader = reader
        self._snapshot = snapshot
        self._quota_blocked = quota_blocked
        self._clock = clock
        self._cache_for = cache_for
        self._recorded = {
            instrument.symbol.upper() for section in snapshot.sections for instrument in section.instruments
        }
        self._cached: MtfInstrumentCatalog | None = None
        self._cache_until: datetime | None = None

    async def catalog(self) -> MtfInstrumentCatalog:
        if not self._quota_blocked():
            return self._snapshot
        now = self._clock()
        if self._cached is not None and self._cache_until is not None and now < self._cache_until:
            return self._cached
        try:
            groups = parse_bridge_sequence(await self._reader.watchlist_payload())
            check_matches_recorded(groups, self._recorded, self._snapshot.watchlist_name)
            result = self._from_visible(symbols_of(groups), groups, now)
        except (DataSourceUnavailableError, WatchlistUnavailableError):
            result = self._snapshot
        self._cached = result
        self._cache_until = now + self._cache_for
        return result

    def _from_visible(self, visible: set[str], groups, now: datetime) -> MtfInstrumentCatalog:
        ordered_visible = [item.symbol.upper() for group in groups for item in group.instruments]
        display = {item.symbol.upper(): item.display_name for group in groups for item in group.instruments}
        sections: list[MtfInstrumentSection] = []
        for section in self._snapshot.sections:
            instruments = [
                MtfInstrument(symbol=instrument.symbol.upper(), display_name=instrument.display_name)
                for instrument in section.instruments
                if instrument.symbol.upper() in visible
            ]
            if instruments:
                sections.append(MtfInstrumentSection(name=section.name, instruments=instruments))
        extra = [
            MtfInstrument(symbol=symbol, display_name=display[symbol])
            for symbol in ordered_visible
            if symbol not in self._recorded
        ]
        if extra:
            sections.append(MtfInstrumentSection(name=UNSECTIONED_NAME, instruments=extra))
        symbols = [item.symbol for section in sections for item in section.instruments]
        default = self._snapshot.default_symbol.upper()
        return MtfInstrumentCatalog(
            watchlist_name=self._snapshot.watchlist_name,
            recorded_at=now,
            default_symbol=default if default in symbols else symbols[0],
            sections=sections,
            origin=CATALOG_ORIGIN_DESKTOP,
        )


def _symbols_of(catalog: MtfInstrumentCatalog) -> set[str]:
    return {instrument.symbol for section in catalog.sections for instrument in section.instruments}


class MultiTimeframeAnalysisService:
    def __init__(
        self,
        orchestrator: MultiTimeframeContextOrchestrator,
        *,
        catalog: Optional[MtfInstrumentCatalog] = None,
        catalog_source: Optional[MtfCatalogSource] = None,
        thresholds: Optional[ChecklistThresholds] = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._orchestrator = orchestrator
        self._snapshot = catalog or load_instrument_catalog()
        self._catalog_source = catalog_source
        self._thresholds = thresholds or ChecklistThresholds()
        self._clock = clock

    async def current_catalog(self) -> MtfInstrumentCatalog:
        """The list the page should offer right now: the snapshot, or the visible Desktop watchlist during fallback."""
        if self._catalog_source is None:
            return self._snapshot
        return await self._catalog_source.catalog()

    async def is_known(self, symbol: str) -> bool:
        return symbol.strip().upper() in _symbols_of(await self.current_catalog())

    async def analyze(self, symbol: str, *, force_refresh: bool = False) -> MultiTimeframeAnalysis:
        normalized = symbol.strip().upper()
        catalog = await self.current_catalog()
        if normalized not in _symbols_of(catalog):
            raise UnknownInstrumentError(
                f"{normalized or 'The symbol'} is not in the {catalog.watchlist_name} list."
            )

        timeframes = default_mtf_timeframes()
        context = await self._orchestrator.get_context(normalized, timeframes=timeframes, force_refresh=force_refresh)
        results: Dict[AnalysisTimeframe, TimeframeContextResult] = dict(context.contexts)
        stale = [
            tf for tf, result in results.items()
            if result.context is not None and result.context.freshness_state is SourceState.STALE
        ]
        if stale:
            refreshed = await self._orchestrator.get_context(normalized, timeframes=stale, force_refresh=True)
            for tf, result in refreshed.contexts.items():
                if result.context is not None:
                    results[tf] = result

        now = self._clock()
        evaluations: Dict[AnalysisTimeframe, Optional[TimeframeEvaluation]] = {}
        statuses: Dict[AnalysisTimeframe, MtfTimeframeStatus] = {}
        warnings = []
        for tf in timeframes:
            evaluation, status = self._evaluate(tf, results.get(tf), now)
            evaluations[tf] = evaluation
            statuses[tf] = status
            if status.unavailable_reason:
                warnings.append(f"{tf.value}: {status.unavailable_reason}")

        usable = sum(evaluation is not None and evaluation.series is not None for evaluation in evaluations.values())
        completeness = (
            MultiTimeframeCompleteness.COMPLETE
            if usable == len(timeframes)
            else MultiTimeframeCompleteness.PARTIAL
            if usable
            else MultiTimeframeCompleteness.UNAVAILABLE
        )
        screens = evaluate_screens(evaluations, self._thresholds)
        return MultiTimeframeAnalysis(
            symbol=normalized,
            display_name=display_name(normalized),
            requested_at=now,
            profile_version=self._thresholds.version,
            completeness=completeness,
            timeframes=statuses,
            layers=screens.layers,
            rows=self._rows(evaluations, statuses),
            decisions=MtfDecisions(
                double_screens=screens.double_screens,
                triple_screen=screens.triple_screen,
                disclaimer=DISCLAIMER,
            ),
            warnings=warnings,
        )

    def _evaluate(
        self, tf: AnalysisTimeframe, result: Optional[TimeframeContextResult], now: datetime
    ) -> tuple[Optional[TimeframeEvaluation], MtfTimeframeStatus]:
        if result is None or result.context is None:
            reason = result.unavailable_reason if result else "Timeframe was not requested."
            return None, MtfTimeframeStatus(
                timeframe=tf, freshness_state=SourceState.UNAVAILABLE, unavailable_reason=reason
            )
        ctx = result.context
        status = MtfTimeframeStatus(
            timeframe=tf,
            source=ctx.source,
            source_timestamp=ctx.source_timestamp,
            freshness_state=ctx.freshness_state,
            candle_count=len(ctx.candles),
        )
        if ctx.freshness_state is SourceState.STALE:
            return None, status.model_copy(update={"unavailable_reason": STALE_REASON})
        latest_candle_live = bool(
            ctx.candles
            and is_live_candle(tf, ctx.candles[-1].timestamp, now, exchange_of(ctx.symbol))
        )
        evaluation = evaluate_timeframe(
            ctx.candles,
            self._thresholds,
            latest_candle_live=latest_candle_live,
        )
        if evaluation.series is None:
            return evaluation, status.model_copy(update={"unavailable_reason": evaluation.unavailable_reason})
        return evaluation, status.model_copy(
            update={
                "last_close": evaluation.last_close,
                "live_candle": latest_candle_live,
            }
        )

    def _rows(
        self,
        evaluations: Dict[AnalysisTimeframe, Optional[TimeframeEvaluation]],
        statuses: Dict[AnalysisTimeframe, MtfTimeframeStatus],
    ) -> list[MtfChecklistRow]:
        rows = []
        for row in CHECKLIST_ROWS:
            cells = {}
            if row.automated:
                for tf, evaluation in evaluations.items():
                    if evaluation is not None and row.id in evaluation.cells:
                        cells[tf] = evaluation.cells[row.id]
                    else:
                        cells[tf] = ChecklistCell(
                            bias=Bias.UNAVAILABLE,
                            rule_ids=[row.id],
                            unavailable_reason=statuses[tf].unavailable_reason or "Timeframe is unavailable.",
                        )
            rows.append(
                MtfChecklistRow(id=row.id, section=row.section, label=row.label, automated=row.automated, cells=cells)
            )
        return rows
