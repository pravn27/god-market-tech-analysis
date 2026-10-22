"""A lock that every process uses before it switches the one TradingView Desktop chart.

The live pages and the scheduled data jobs run in separate processes, so an in-process lock is not
enough. This is an operating-system file lock: a process that dies releases it automatically.
"""

from __future__ import annotations

import asyncio
import fcntl
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from .providers import DataSourceUnavailableError

DEFAULT_CHART_LOCK_PATH = Path.home() / ".cache" / "god-market" / "desktop-chart.lock"
POLL_SECONDS = 0.25


class ChartBusyError(DataSourceUnavailableError):
    """Another read is using the TradingView Desktop chart and did not finish in time."""


@asynccontextmanager
async def desktop_chart_lock(path: Path, *, timeout: float) -> AsyncIterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "a+")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    try:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if loop.time() >= deadline:
                    raise ChartBusyError(
                        "TradingView Desktop's chart is in use by another read. Try again shortly."
                    ) from None
                await asyncio.sleep(POLL_SECONDS)
        yield
    finally:
        # Closing the file releases the lock, even if the body raised.
        handle.close()
