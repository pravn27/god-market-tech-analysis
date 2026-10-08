"""Read-only quotes from the active TradingView Desktop watchlist."""

import asyncio
import json
import math
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from .providers import DataSourceUnavailableError

# TradingView renders negative quotes with U+2212 rather than an ASCII hyphen.
_MINUS_SIGNS = str.maketrans({sign: "-" for sign in "\u2212\u2012\u2013\u2014\ufe63\uff0d"})


@dataclass(frozen=True)
class DesktopWatchlistQuote:
    last_price: float | None
    change_percent: float | None


@dataclass(frozen=True)
class DesktopWatchlistQuoteSnapshot:
    quotes: Mapping[str, DesktopWatchlistQuote]
    observed_at: datetime


class TradingViewDesktopWatchlistReader:
    """Read visible active-watchlist quote rows through the local bridge CLI.

    The active watchlist is accepted only when its ordered symbols exactly match
    the approved Global Market universe. The bridge does not expose a reliable
    watchlist name or exchange timestamp in its quote response.
    """

    def __init__(
        self,
        cli_path: str | Path | None,
        *,
        node_executable: str = "node",
        timeout_seconds: float = 8.0,
    ) -> None:
        self._cli_path = Path(cli_path).expanduser() if cli_path else None
        self._node_executable = node_executable
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "TradingViewDesktopWatchlistReader":
        return cls(
            os.environ.get("TRADINGVIEW_DESKTOP_BRIDGE_CLI"),
            node_executable=os.environ.get("TRADINGVIEW_DESKTOP_BRIDGE_NODE") or "node",
        )

    async def get_quotes(self, expected_symbols: Sequence[str]) -> DesktopWatchlistQuoteSnapshot:
        if self._cli_path is None:
            raise DataSourceUnavailableError(
                "The Desktop watchlist fallback is not configured. Set TRADINGVIEW_DESKTOP_BRIDGE_CLI."
            )
        if not self._cli_path.is_file():
            raise DataSourceUnavailableError("The configured TradingView Desktop bridge CLI was not found.")
        if not shutil.which(self._node_executable):
            raise DataSourceUnavailableError("Node.js is not available for the TradingView Desktop bridge.")

        try:
            process = await asyncio.create_subprocess_exec(
                self._node_executable,
                str(self._cli_path),
                "watchlist",
                "get",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
        except (OSError, asyncio.TimeoutError) as error:
            raise DataSourceUnavailableError("The TradingView Desktop watchlist read could not be completed.") from error
        if process.returncode != 0:
            raise DataSourceUnavailableError("The TradingView Desktop watchlist read failed.")
        try:
            payload = json.loads(stdout.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DataSourceUnavailableError("The Desktop bridge returned an unreadable watchlist response.") from error
        return parse_watchlist_payload(payload, expected_symbols)


def parse_watchlist_payload(
    payload: object,
    expected_symbols: Sequence[str],
    *,
    observed_at: datetime | None = None,
) -> DesktopWatchlistQuoteSnapshot:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise DataSourceUnavailableError("The Desktop bridge did not return a usable watchlist.")

    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list) or any(not isinstance(item, dict) for item in raw_symbols):
        raise DataSourceUnavailableError("The Desktop bridge returned no valid watchlist symbols.")
    symbols = [str(item.get("symbol", "")).strip().upper() for item in raw_symbols]
    if symbols != [symbol.upper() for symbol in expected_symbols]:
        raise DataSourceUnavailableError(
            "The visible Desktop watchlist does not match the approved PS_Global_Indices symbols and order."
        )

    quotes = {
        str(item["symbol"]).strip().upper(): DesktopWatchlistQuote(
            last_price=_parse_number(item.get("last")),
            change_percent=_parse_number(item.get("change_percent"), percent=True),
        )
        for item in raw_symbols
    }
    return DesktopWatchlistQuoteSnapshot(
        quotes=quotes,
        observed_at=observed_at or datetime.now(timezone.utc),
    )


def _parse_number(value: object, *, percent: bool = False) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        number = float(value)
    elif isinstance(value, str):
        cleaned = value.strip().replace(",", "").translate(_MINUS_SIGNS)
        if percent:
            cleaned = cleaned.removesuffix("%").strip()
        try:
            number = float(cleaned)
        except ValueError:
            return None
    else:
        return None
    return number if math.isfinite(number) else None
