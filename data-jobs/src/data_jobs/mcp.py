"""Daily bars from the TradingView official MCP.

Only daily bars come from here. Weekly, monthly and quarterly bars are derived from the stored daily
bars. A quota block is raised as the fallback's quota signal, so the Desktop chart can take over.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from god_market_api.providers import OfficialQuotaExceededError

from .candles import daily_bars
from .fallback import QuotaExhaustedError
from .runner import FetchResult
from .store import utc_now

DAILY = "1D"
MCP_SOURCE = "official_mcp"


class OfficialMcpDailyFetcher:
    def __init__(
        self,
        provider: Any,
        *,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        clock: Callable[[], Any] = utc_now,
    ) -> None:
        self._provider = provider
        self._loop = loop or asyncio.new_event_loop()
        self._clock = clock

    @classmethod
    def from_environment(cls) -> "OfficialMcpDailyFetcher":
        from god_market_api.oauth import OfficialMCPOAuthCoordinator
        from god_market_api.providers import OfficialMCPProvider

        return cls(OfficialMCPProvider(tool_caller=OfficialMCPOAuthCoordinator()))

    def fetch(self, symbol: str, timeframe: str, *, count: int) -> FetchResult:
        if timeframe != DAILY:
            raise ValueError("The official MCP fetcher reads daily bars; other periods are derived from them.")
        try:
            context = self._loop.run_until_complete(
                self._provider.get_price_context(symbol, DAILY, candle_count=count)
            )
        except OfficialQuotaExceededError as error:
            raise QuotaExhaustedError(str(error)) from error
        return FetchResult(bars=daily_bars(context.candles, count=count, now=self._clock()), source=MCP_SOURCE)
