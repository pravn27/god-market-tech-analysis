"""Use case: PAPA + SMM multi-timeframe checklist for one watchlist instrument."""

import json
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional

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

SNAPSHOT_PATH = Path(__file__).parent / "data" / "ps_dailywatch_favourite.json"

DISPLAY_NAMES = {
    "NSE:NIFTY": "Nifty 50",
    "NSE:BANKNIFTY": "Nifty Bank",
    "NSE:INDIAVIX": "India VIX",
}

STALE_REASON = "Cached data is stale and could not be refreshed."

IST = timezone(timedelta(hours=5, minutes=30))
NSE_SESSION_CLOSE = time(15, 30)

_PERIODS = {
    AnalysisTimeframe.FOUR_HOUR: timedelta(hours=4),
    AnalysisTimeframe.ONE_HOUR: timedelta(hours=1),
    AnalysisTimeframe.FIFTEEN_MINUTE: timedelta(minutes=15),
}


class UnknownInstrumentError(ValueError):
    """The symbol is not part of the recorded watchlist snapshot."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def display_name(symbol: str) -> str:
    return DISPLAY_NAMES.get(symbol, symbol.split(":")[-1])


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


def _session_close(day: date) -> datetime:
    return datetime.combine(day, NSE_SESSION_CLOSE, IST)


def candle_closes_at(timeframe: AnalysisTimeframe, opened_at: datetime) -> datetime:
    """When the candle's last NSE session ends. NSE holidays are not modelled."""
    opened = opened_at.astimezone(IST)
    if timeframe is AnalysisTimeframe.MONTHLY:
        next_month = (opened.replace(day=28) + timedelta(days=4)).replace(day=1).date()
        last_day = next_month - timedelta(days=1)
        while last_day.weekday() > 4:
            last_day -= timedelta(days=1)
        return _session_close(last_day)
    if timeframe is AnalysisTimeframe.WEEKLY:
        return _session_close(opened.date() + timedelta(days=4 - opened.weekday()))
    if timeframe is AnalysisTimeframe.DAILY:
        return _session_close(opened.date())
    return min(opened_at + _PERIODS[timeframe], _session_close(opened.date()))


def is_live_candle(timeframe: AnalysisTimeframe, opened_at: datetime, now: datetime) -> bool:
    """Whether the latest candle can still change, i.e. its last NSE session has not closed."""
    return now < candle_closes_at(timeframe, opened_at)


class MultiTimeframeAnalysisService:
    def __init__(
        self,
        orchestrator: MultiTimeframeContextOrchestrator,
        *,
        catalog: Optional[MtfInstrumentCatalog] = None,
        thresholds: Optional[ChecklistThresholds] = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._orchestrator = orchestrator
        self._catalog = catalog or load_instrument_catalog()
        self._thresholds = thresholds or ChecklistThresholds()
        self._clock = clock
        self._symbols = {
            instrument.symbol for section in self._catalog.sections for instrument in section.instruments
        }

    @property
    def catalog(self) -> MtfInstrumentCatalog:
        return self._catalog

    async def analyze(self, symbol: str, *, force_refresh: bool = False) -> MultiTimeframeAnalysis:
        normalized = symbol.strip().upper()
        if normalized not in self._symbols:
            raise UnknownInstrumentError(
                f"{normalized or 'The symbol'} is not in the {self._catalog.watchlist_name} snapshot."
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
        evaluation = evaluate_timeframe(ctx.candles, self._thresholds)
        if evaluation.series is None:
            return evaluation, status.model_copy(update={"unavailable_reason": evaluation.unavailable_reason})
        return evaluation, status.model_copy(
            update={
                "last_close": evaluation.last_close,
                "live_candle": is_live_candle(tf, evaluation.last_candle_at, now),
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
