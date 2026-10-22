"""Official MCP first. TradingView Desktop's open chart only when the MCP quota is used up.

Only a quota error triggers the fallback. Other MCP failures are reported as they are. The fallback
reads daily bars only, because each Desktop read switches the chart. Weekly, monthly and quarterly
bars wait for the MCP quota.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, List, Protocol

from .runner import BarFetcher, FetchResult
from .store import Bar, utc_now

DAILY = "1D"
DESKTOP_SOURCE = "desktop_bridge"
# Enough for one pass over the watchlist plus the in-run retry of every failed item.
DEFAULT_DESKTOP_READ_BUDGET = 80


class QuotaExhaustedError(Exception):
    """The official MCP daily quota is used up. The message is the reason shown in status."""


class DesktopDailyReader(Protocol):
    def is_open(self) -> bool:
        ...

    def read_daily(self, symbol: str, *, count: int, now: datetime) -> List[Bar]:
        ...


class FallbackFetcher:
    """Create one per run: the Desktop read budget counts only the reads made by this instance."""

    def __init__(
        self,
        primary: BarFetcher,
        desktop: DesktopDailyReader,
        *,
        budget: int = DEFAULT_DESKTOP_READ_BUDGET,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if budget < 0:
            raise ValueError("The Desktop read budget cannot be negative.")
        self._primary = primary
        self._desktop = desktop
        self._budget = budget
        self._clock = clock
        self.desktop_reads = 0

    def fetch(self, symbol: str, timeframe: str, *, count: int) -> FetchResult:
        try:
            return self._primary.fetch(symbol, timeframe, count=count)
        except QuotaExhaustedError as quota:
            reason = str(quota)

        if timeframe != DAILY:
            raise QuotaExhaustedError(
                f"{reason} Only daily bars can come from the Desktop chart, so this item waits for the MCP quota."
            )
        if self.desktop_reads >= self._budget:
            raise QuotaExhaustedError(
                f"{reason} The Desktop read limit of {self._budget} for this run is used up."
            )
        if not self._desktop.is_open():
            raise QuotaExhaustedError(f"{reason} TradingView Desktop is not open and responding.")

        self.desktop_reads += 1
        bars = self._desktop.read_daily(symbol, count=count, now=self._clock())
        return FetchResult(bars=bars, source=DESKTOP_SOURCE)
