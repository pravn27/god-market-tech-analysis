"""Stable internal models shared by data sources, rules, and the dashboard."""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    OFFICIAL_MCP = "official_mcp"
    DESKTOP_BRIDGE = "desktop_bridge"


class SourceState(str, Enum):
    READY = "ready"
    UNAVAILABLE = "unavailable"
    STALE = "stale"
    NOT_CONFIGURED = "not_configured"


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


class ServiceHealth(BaseModel):
    service: str = "god-market-mcp-api"
    state: str = "ok"
    sources: List[SourceHealth]
