"""Stable internal models shared by data sources, rules, and the dashboard."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class DataSource(str, Enum):
    OFFICIAL_MCP = "official_mcp"
    DESKTOP_BRIDGE = "desktop_bridge"
    FIXTURE = "fixture"


class SourceState(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    NOT_CONFIGURED = "not_configured"


class AnalysisTimeframe(str, Enum):
    """User-facing timeframe identifiers for the multi-timeframe analysis."""

    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    FOUR_HOUR = "4h"
    ONE_HOUR = "1h"
    FIFTEEN_MINUTE = "15m"


class MultiTimeframeCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class GlobalMarketCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class DesktopFallbackState(str, Enum):
    """How much of a snapshot's available evidence came from the Desktop watchlist."""

    NONE = "none"
    PARTIAL = "partial"
    FULL = "full"


class MarketDirection(str, Enum):
    """Evidence-only price movement state for one global-market item."""

    ADVANCING = "advancing"
    DECLINING = "declining"
    UNCHANGED = "unchanged"
    UNAVAILABLE = "unavailable"


class MultiTimeframeLayer(BaseModel):
    """One decision layer references two already-requested timeframe contexts."""

    name: str
    timeframes: tuple[AnalysisTimeframe, AnalysisTimeframe]


def default_mtf_timeframes() -> tuple[AnalysisTimeframe, ...]:
    """Return the unique timeframes required for the initial Confluence Board."""
    return (
        AnalysisTimeframe.MONTHLY,
        AnalysisTimeframe.WEEKLY,
        AnalysisTimeframe.DAILY,
        AnalysisTimeframe.FOUR_HOUR,
        AnalysisTimeframe.ONE_HOUR,
        AnalysisTimeframe.FIFTEEN_MINUTE,
    )


def default_mtf_layers() -> tuple[MultiTimeframeLayer, ...]:
    """Map timeframe evidence into the established Super TIDE-to-Ripple layers."""
    return (
        MultiTimeframeLayer(
            name="Super TIDE",
            timeframes=(AnalysisTimeframe.MONTHLY, AnalysisTimeframe.WEEKLY),
        ),
        MultiTimeframeLayer(
            name="TIDE",
            timeframes=(AnalysisTimeframe.DAILY, AnalysisTimeframe.FOUR_HOUR),
        ),
        MultiTimeframeLayer(
            name="WAVE",
            timeframes=(AnalysisTimeframe.FOUR_HOUR, AnalysisTimeframe.ONE_HOUR),
        ),
        MultiTimeframeLayer(
            name="Ripple / Super Ripple",
            timeframes=(AnalysisTimeframe.ONE_HOUR, AnalysisTimeframe.FIFTEEN_MINUTE),
        ),
    )


class SourceHealth(BaseModel):
    source: DataSource
    state: SourceState
    detail: str
    checked_at: datetime
    last_success_at: Optional[datetime] = None


class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


class TechnicalSnapshot(BaseModel):
    """Single-timeframe snapshot from a source, without strategy interpretation."""

    recommendation: Optional[str] = None
    summary: Optional[str] = None
    moving_averages: Optional[str] = None
    oscillators: Optional[str] = None
    values: Dict[str, float] = Field(default_factory=dict)


class ChartContext(BaseModel):
    """Normalized, source-attributed context consumed by the local rules engine."""

    symbol: str
    timeframe: str
    source: DataSource
    source_timestamp: datetime
    freshness_state: SourceState
    candles: List[Candle] = Field(default_factory=list)
    technicals: Optional[TechnicalSnapshot] = None
    warnings: List[str] = Field(default_factory=list)


class GlobalMarketInstrument(BaseModel):
    """One source-attributed watchlist item, without a trade interpretation."""

    symbol: str
    display_name: str
    last_price: Optional[float] = None
    change_percent: Optional[float] = None
    direction: MarketDirection
    source: DataSource
    source_timestamp: Optional[datetime] = None
    freshness_state: SourceState
    warnings: List[str] = Field(default_factory=list)
    unavailable_reason: Optional[str] = None

    @model_validator(mode="after")
    def require_explicit_availability(self):
        if self.direction is MarketDirection.UNAVAILABLE and not self.unavailable_reason:
            raise ValueError("unavailable_reason is required when direction is unavailable.")
        if self.direction is not MarketDirection.UNAVAILABLE and self.last_price is None:
            raise ValueError("last_price is required when direction is available.")
        return self


class GlobalMarketGroup(BaseModel):
    """An ordered section read from the user's TradingView watchlist."""

    name: str = Field(min_length=1)
    instruments: List[GlobalMarketInstrument] = Field(default_factory=list)


class GlobalMarketBreadth(BaseModel):
    """Counts derived from available directional evidence only."""

    advancing: int = Field(ge=0)
    declining: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    unavailable: int = Field(ge=0)


class GlobalMarketSnapshot(BaseModel):
    """Ordered, source-attributed global-market context for the local dashboard."""

    watchlist_name: str
    read_at: datetime
    timeframe: str
    completeness: GlobalMarketCompleteness
    desktop_fallback: DesktopFallbackState = DesktopFallbackState.NONE
    groups: List[GlobalMarketGroup] = Field(default_factory=list)
    breadth: GlobalMarketBreadth
    warnings: List[str] = Field(default_factory=list)


class TimeframeContextResult(BaseModel):
    """A successful context or an explicit reason why it is unavailable."""

    timeframe: AnalysisTimeframe
    context: Optional[ChartContext] = None
    unavailable_reason: Optional[str] = None

    @model_validator(mode="after")
    def require_one_outcome(self):
        if (self.context is None) == (self.unavailable_reason is None):
            raise ValueError("Provide exactly one of context or unavailable_reason.")
        return self


class MultiTimeframeContext(BaseModel):
    """Source-attributed contexts and layer references for one symbol refresh."""

    symbol: str
    requested_at: datetime
    completeness: MultiTimeframeCompleteness
    contexts: Dict[AnalysisTimeframe, TimeframeContextResult]
    layers: List[MultiTimeframeLayer] = Field(default_factory=lambda: list(default_mtf_layers()))
    warnings: List[str] = Field(default_factory=list)


class ServiceHealth(BaseModel):
    service: str = "god-market-mcp-api"
    state: str = "ok"
    sources: List[SourceHealth]
