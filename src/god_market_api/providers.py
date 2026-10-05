"""Provider boundary for TradingView MCP sources.

The application never reads the Codex desktop OAuth credential store. The official
provider will receive its own application-managed OAuth implementation in a later
connector task. Until then, it explicitly reports unavailable rather than fabricating
or reusing market data.
"""

from datetime import datetime, timezone
from typing import Protocol

from .models import ChartContext, DataSource, SourceHealth, SourceState


class DataSourceUnavailableError(RuntimeError):
    """Raised when a source cannot provide fresh context for a request."""


class ChartContextProvider(Protocol):
    async def health(self) -> SourceHealth:
        ...

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        ...


class OfficialMCPProvider:
    """Primary provider placeholder with safe, observable unavailable behaviour."""

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source=DataSource.OFFICIAL_MCP,
            state=SourceState.NOT_CONFIGURED,
            detail=(
                "Official MCP application client is not configured. "
                "Codex OAuth credentials are intentionally not reused by this service."
            ),
            checked_at=datetime.now(timezone.utc),
        )

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        raise DataSourceUnavailableError(
            "Official TradingView MCP is not configured for the local service. "
            "No chart context was returned."
        )
