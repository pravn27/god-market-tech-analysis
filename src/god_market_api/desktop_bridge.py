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

from .models import DataSource, SourceHealth, SourceState
from .providers import DataSourceUnavailableError

# TradingView renders negative quotes with U+2212 rather than an ASCII hyphen.
_MINUS_SIGNS = str.maketrans({sign: "-" for sign in "\u2212\u2012\u2013\u2014\ufe63\uff0d"})

DESKTOP_START_HINT = (
    "Start TradingView Desktop with remote debugging (scripts/start-local.sh) and select PS_Global_Indices."
)


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

    Only rows whose symbols belong to the approved Global Market universe are
    used, and the read is rejected when most visible rows are other symbols. The
    bridge does not expose a reliable watchlist name or exchange timestamp in its
    quote response.
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
        self._last_success_at: datetime | None = None
        self._last_error: str | None = None

    @classmethod
    def from_environment(cls) -> "TradingViewDesktopWatchlistReader":
        return cls(
            os.environ.get("TRADINGVIEW_DESKTOP_BRIDGE_CLI"),
            node_executable=os.environ.get("TRADINGVIEW_DESKTOP_BRIDGE_NODE") or "node",
        )

    async def health(self) -> SourceHealth:
        if self._cli_path is None:
            state, detail = SourceState.NOT_CONFIGURED, "Set TRADINGVIEW_DESKTOP_BRIDGE_CLI to enable the Desktop fallback."
        elif self._last_error is not None:
            state, detail = SourceState.UNAVAILABLE, self._last_error
        elif self._last_success_at is None:
            state, detail = SourceState.NOT_CONFIGURED, "The Desktop watchlist has not been read yet."
        else:
            state, detail = SourceState.READY, "The Desktop watchlist fallback is ready."
        return SourceHealth(
            source=DataSource.DESKTOP_BRIDGE,
            state=state,
            detail=detail,
            checked_at=datetime.now(timezone.utc),
            last_success_at=self._last_success_at,
        )

    async def get_quotes(self, expected_symbols: Sequence[str]) -> DesktopWatchlistQuoteSnapshot:
        try:
            snapshot = await self._read_quotes(expected_symbols)
        except DataSourceUnavailableError as error:
            self._last_error = str(error)
            raise
        self._last_error = None
        self._last_success_at = snapshot.observed_at
        return snapshot

    async def _read_quotes(self, expected_symbols: Sequence[str]) -> DesktopWatchlistQuoteSnapshot:
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
        except OSError as error:
            raise DataSourceUnavailableError("The TradingView Desktop watchlist read could not be started.") from error
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self._timeout_seconds)
        except asyncio.TimeoutError as error:
            process.kill()
            await process.wait()
            raise DataSourceUnavailableError(
                f"The TradingView Desktop watchlist read timed out. {DESKTOP_START_HINT}"
            ) from error
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise
        if process.returncode != 0:
            raise DataSourceUnavailableError(f"The TradingView Desktop watchlist read failed. {DESKTOP_START_HINT}")
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
    approved = {symbol.upper() for symbol in expected_symbols}
    rows = {str(item.get("symbol", "")).strip().upper(): item for item in raw_symbols}
    rows.pop("", None)
    matched = {symbol: item for symbol, item in rows.items() if symbol in approved}
    # A majority of foreign rows means another watchlist is selected; never borrow its quotes.
    if not matched or len(matched) * 2 <= len(rows):
        raise DataSourceUnavailableError(
            "The visible Desktop watchlist is not PS_Global_Indices; select it in TradingView Desktop."
        )

    quotes = {
        symbol: DesktopWatchlistQuote(
            last_price=_parse_number(item.get("last")),
            change_percent=_parse_number(item.get("change_percent"), percent=True),
        )
        for symbol, item in matched.items()
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
