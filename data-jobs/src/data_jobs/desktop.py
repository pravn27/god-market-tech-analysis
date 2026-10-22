"""Daily bars from the open TradingView Desktop chart, for the fallback.

This wraps the live app's chart reader, so both use the same switch-and-restore logic and the same
cross-process chart lock. The reader is used from synchronous job code, so it drives one event loop.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import List, Optional

from god_market_api.desktop_bridge import TradingViewDesktopCli
from god_market_api.desktop_candles import CHART_COMMAND_TIMEOUT_SECONDS, DesktopChartCandleProvider
from god_market_api.providers import DataSourceUnavailableError

from .candles import daily_bars
from .store import Bar

DAILY_INTERVAL = "1D"


class DesktopChartDailyReader:
    def __init__(
        self,
        *,
        provider: DesktopChartCandleProvider,
        cli: TradingViewDesktopCli,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> None:
        self._provider = provider
        self._cli = cli
        self._loop = loop or asyncio.new_event_loop()

    @classmethod
    def from_environment(cls) -> "DesktopChartDailyReader":
        return cls(
            provider=DesktopChartCandleProvider.from_environment(),
            cli=TradingViewDesktopCli.from_environment(timeout_seconds=CHART_COMMAND_TIMEOUT_SECONDS),
        )

    def is_open(self) -> bool:
        """Open and responding: the bridge reports success, a connected debugger and an available chart API."""
        try:
            payload = self._loop.run_until_complete(self._cli.run("status"))
        except DataSourceUnavailableError:
            return False
        return (
            isinstance(payload, dict)
            and payload.get("success") is True
            and payload.get("cdp_connected") is True
            and payload.get("api_available") is True
        )

    def read_daily(self, symbol: str, *, count: int, now: datetime) -> List[Bar]:
        context = self._loop.run_until_complete(self._provider.get_chart_context(symbol, DAILY_INTERVAL))
        return daily_bars(context.candles, count=count, now=now)
