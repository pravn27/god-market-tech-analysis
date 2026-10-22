"""Jobs that the scheduled run executes.

The Global Market instrument list is read from the open TradingView Desktop watchlist
``PS_Global_Indices``. Reading it costs no MCP quota, but TradingView Desktop must be open with that
watchlist visible. When it is not, the jobs cannot be built and the run says why.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Callable, Tuple

from god_market_api.desktop_bridge import TradingViewDesktopWatchlistReader
from god_market_api.global_market import WatchlistUnavailableError
from god_market_api.watchlist_source import DesktopWatchlistSectionSource

from .aggregate import MONTHLY, QUARTERLY, WEEKLY
from .desktop import DesktopChartDailyReader
from .fallback import FallbackFetcher
from .mcp import OfficialMcpDailyFetcher
from .runner import BarFetcher, JobSpec
from .trading_day import trading_day

GLOBAL_MARKET_DAILY = "global-market-daily"
# Daily bars kept per symbol and read on every run. Weekly, monthly and quarterly bars are built from
# the stored history, so this window only has to cover the newest days that are not yet stored.
DAILY_BAR_COUNT = 300
DERIVED_PERIODS = (WEEKLY, MONTHLY, QUARTERLY)


class InstrumentListUnavailable(Exception):
    """The Global Market instruments cannot be read. The message is shown to the user as the reason."""


def global_market_symbols(
    reader_factory: Callable[[], TradingViewDesktopWatchlistReader] = TradingViewDesktopWatchlistReader.from_environment,
) -> Tuple[str, ...]:
    """Every instrument in ``PS_Global_Indices``, in on-screen order, without duplicates."""
    source = DesktopWatchlistSectionSource(reader_factory())
    try:
        read = asyncio.run(source.read())
    except WatchlistUnavailableError as error:
        raise InstrumentListUnavailable(str(error)) from error
    symbols = []
    for group in read.groups:
        for instrument in group.instruments:
            if instrument.symbol not in symbols:
                symbols.append(instrument.symbol)
    if not symbols:
        raise InstrumentListUnavailable("The Desktop watchlist has no instruments.")
    return tuple(symbols)


def registered_jobs() -> Tuple[JobSpec, ...]:
    return (
        JobSpec(
            name=GLOBAL_MARKET_DAILY,
            interval=timedelta(days=1),
            symbols=global_market_symbols(),
            timeframes=("1D",),
            bar_count=DAILY_BAR_COUNT,
            derived_periods=DERIVED_PERIODS,
            trading_day=trading_day,
        ),
    )


def bar_source() -> BarFetcher:
    """Official MCP first; the open Desktop chart only when the MCP quota is used up. One per run."""
    return FallbackFetcher(
        OfficialMcpDailyFetcher.from_environment(),
        DesktopChartDailyReader.from_environment(),
    )
