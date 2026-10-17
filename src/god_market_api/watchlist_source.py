"""Read the Global Market watchlist sections from the official TradingView MCP (read-only).

The list operation returns each watchlist with its symbols. Section headers are
symbols that start with ``###`` (for example ``###USA``); every symbol after a
header belongs to that section. Only list operations are used here. The
active-watchlist operation is never called, because it can change which
watchlist is active in TradingView.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Protocol, Sequence

from .desktop_bridge import TradingViewDesktopWatchlistReader
from .global_market import (
    RECORDED_WATCHLIST_GROUPS,
    WATCHLIST_NAME,
    WATCHLIST_ORIGIN_DESKTOP,
    WatchlistGroupDefinition,
    WatchlistGroupSource,
    WatchlistInstrumentDefinition,
    WatchlistRead,
    WatchlistUnavailableError,
)
from .providers import DataSourceUnavailableError


LIST_WATCHLISTS_TOOL = "mcp-watchlist-list-watchlists"
SECTION_PREFIX = "###"

# The MCP returns tickers only, so display names are looked up here. A symbol
# missing from this map is shown by its ticker, which keeps new rows visible.
DISPLAY_NAMES: Mapping[str, str] = {
    "TVC:DJI": "Dow Jones Industrial Average",
    "DJCFD:DJT": "Dow Jones Transportation Average",
    "NASDAQ:NDX": "Nasdaq 100",
    "CBOE:MAGS": "Magnificent 7 Index",
    "NASDAQ:IXIC": "Nasdaq Composite",
    "VANTAGE:USDINR": "USD / INR",
    "TVC:SPX": "S&P 500",
    "BLACKBULL:DJ30.F": "Dow Jones 30 Futures",
    "BLACKBULL:US30": "US Wall Street 30",
    "TVC:NYA": "NYSE Composite",
    "CBOEFTSE:RUT": "Russell 2000",
    "TVC:DXY": "US Dollar Currency Index",
    "TVC:VIX": "CBOE Volatility Index",
    "TVC:US10Y": "US 10 Year Government Bond Yield",
    "TVC:SX5E": "EURO STOXX 50 Index",
    "XETR:DAX": "DAX",
    "TVC:CAC40": "CAC 40",
    "FTSE:UKX": "FTSE 100",
    "NSEIX:NIFTY1!": "GIFT Nifty 50 Futures",
    "TVC:NI225": "Nikkei 225",
    "TVC:HSI": "Hang Seng Index",
    "SSE:000300": "CSI 300 Index",
    "SSE:000001": "SSE Composite Index",
    "KRX:KOSPI": "KOSPI Composite Index",
    "TWSE:TAIEX": "Taiwan Weighted Index",
    "ASX:XJO": "S&P/ASX 200",
    "TVC:STI": "Straits Times Index",
    "IDX:COMPOSITE": "IDX Composite",
    "SET:SET": "SET Index",
    "NYSE:HDB": "HDFC Bank ADR",
    "NYSE:IBN": "ICICI Bank ADR",
    "NYSE:INFY": "Infosys ADR",
    "NYSE:WIT": "Wipro ADR",
    "NYSE:RDY": "Dr. Reddy's ADR",
}

_UNSECTIONED = "WATCHLIST"


class MCPToolCaller(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


def parse_watchlist_groups(
    symbols: Sequence[str], display_names: Mapping[str, str] = DISPLAY_NAMES
) -> tuple[WatchlistGroupDefinition, ...]:
    """Split a watchlist's symbol list into sections at each ``###`` header.

    Headers with no instruments are dropped. Symbols that appear before the
    first header go into a section named ``WATCHLIST``.
    """
    sections: list[tuple[str, list[WatchlistInstrumentDefinition]]] = []
    for raw in symbols:
        entry = raw.strip()
        if not entry:
            continue
        if entry.startswith(SECTION_PREFIX):
            sections.append((entry[len(SECTION_PREFIX) :].strip(), []))
            continue
        if not sections:
            sections.append((_UNSECTIONED, []))
        ticker = entry.split(":")[-1]
        name = display_names.get(entry.upper(), ticker)
        sections[-1][1].append(WatchlistInstrumentDefinition(symbol=entry, display_name=name))
    return tuple(
        WatchlistGroupDefinition(name=name, instruments=tuple(items)) for name, items in sections if items
    )


def _result_text(result: Any) -> str:
    if getattr(result, "isError", False):
        raise RuntimeError("the TradingView MCP reported an error for the watchlist list")
    return "".join(getattr(item, "text", "") or "" for item in getattr(result, "content", None) or [])


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OfficialWatchlistSource:
    """Watchlist sections read through the official MCP, cached between refreshes.

    A failed live read returns the last good reading and says why. Only when no
    reading has ever succeeded does it raise ``WatchlistUnavailableError``.
    """

    def __init__(
        self,
        caller: MCPToolCaller,
        *,
        watchlist_name: str = WATCHLIST_NAME,
        clock: Callable[[], datetime] = _utc_now,
        cache_for: timedelta = timedelta(minutes=5),
    ) -> None:
        if cache_for < timedelta(0):
            raise ValueError("cache_for must not be negative.")
        self._caller = caller
        self._watchlist_name = watchlist_name
        self._clock = clock
        self._cache_for = cache_for
        self._lock = asyncio.Lock()
        self._last_good: WatchlistRead | None = None
        self._cache_until: datetime | None = None

    async def read(self) -> WatchlistRead:
        async with self._lock:
            now = self._clock()
            if self._last_good is not None and self._cache_until is not None and now < self._cache_until:
                return self._last_good
            try:
                groups = await self._read_live()
            except Exception as error:  # noqa: BLE001 - any failure falls back to the last good reading
                reason = str(error) or type(error).__name__
                if self._last_good is not None:
                    return replace(self._last_good, error=reason)
                raise WatchlistUnavailableError(reason) from error
            self._last_good = WatchlistRead(groups=groups, read_at=now)
            self._cache_until = now + self._cache_for
            return self._last_good

    async def _read_live(self) -> tuple[WatchlistGroupDefinition, ...]:
        result = await self._caller.call_tool(LIST_WATCHLISTS_TOOL, {})
        payload = json.loads(_result_text(result))
        for watchlist in payload.get("watchlists", []):
            if watchlist.get("name") == self._watchlist_name:
                groups = parse_watchlist_groups(watchlist.get("symbols") or [])
                if not groups:
                    raise WatchlistUnavailableError(f"{self._watchlist_name} has no instruments.")
                return groups
        raise WatchlistUnavailableError(f"{self._watchlist_name} was not found in the TradingView account.")


def parse_bridge_sequence(
    payload: object, display_names: Mapping[str, str] = DISPLAY_NAMES
) -> tuple[WatchlistGroupDefinition, ...]:
    """Sections from the Desktop bridge's ordered ``sequence`` (headers and symbols in on-screen order).

    The bridge marks headers as ``{"section": "USA"}`` and rows as ``{"symbol": "TVC:SPX"}``. They are
    converted to the same ``###`` form the MCP uses, so both sources share one parser.
    """
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise WatchlistUnavailableError("The TradingView Desktop bridge did not return a usable watchlist.")
    sequence = payload.get("sequence")
    if not isinstance(sequence, list):
        raise WatchlistUnavailableError("The TradingView Desktop bridge did not return watchlist sections.")
    entries: list[str] = []
    for item in sequence:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("section"), str):
            entries.append(f"{SECTION_PREFIX}{item['section']}")
        elif isinstance(item.get("symbol"), str):
            entries.append(item["symbol"])
    return parse_watchlist_groups(entries, display_names=display_names)


def _check_is_global_indices(groups: Sequence[WatchlistGroupDefinition]) -> None:
    """Reject a Desktop watchlist that is not PS_Global_Indices.

    The bridge does not report the watchlist name, so the visible rows are compared with the recorded
    snapshot: at least three quarters of it must be present and at most a quarter of the rows may be new.
    """
    recorded = {item.symbol.upper() for group in RECORDED_WATCHLIST_GROUPS for item in group.instruments}
    rows = {item.symbol.upper() for group in groups for item in group.instruments}
    if not rows:
        raise WatchlistUnavailableError("The visible TradingView Desktop watchlist has no instruments.")
    present = len(rows & recorded)
    if present * 4 < len(recorded) * 3 or (len(rows) - present) * 4 > len(rows):
        raise WatchlistUnavailableError(
            "The visible TradingView Desktop watchlist is not PS_Global_Indices; select it in TradingView Desktop."
        )


class DesktopWatchlistSectionSource:
    """Watchlist sections read from the visible TradingView Desktop watchlist (read-only)."""

    def __init__(
        self,
        reader: TradingViewDesktopWatchlistReader,
        *,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._reader = reader
        self._clock = clock

    async def read(self) -> WatchlistRead:
        try:
            payload = await self._reader.watchlist_payload()
        except DataSourceUnavailableError as error:
            raise WatchlistUnavailableError(str(error)) from error
        groups = parse_bridge_sequence(payload)
        _check_is_global_indices(groups)
        return WatchlistRead(groups=groups, read_at=self._clock(), origin=WATCHLIST_ORIGIN_DESKTOP)


class FallbackWatchlistSource:
    """Try the official MCP first; if its live read fails, use the Desktop bridge; then keep older data.

    Order: official MCP live reading, then the TradingView Desktop watchlist, then the official
    last good reading (marked stale). The recorded snapshot is applied by the provider when all fail.
    """

    def __init__(self, primary: WatchlistGroupSource, secondary: WatchlistGroupSource) -> None:
        self._primary = primary
        self._secondary = secondary

    async def read(self) -> WatchlistRead:
        primary_read: WatchlistRead | None = None
        try:
            primary_read = await self._primary.read()
        except WatchlistUnavailableError as error:
            primary_reason = str(error)
        else:
            if primary_read.error is None:
                return primary_read
            primary_reason = primary_read.error

        try:
            desktop_read = await self._secondary.read()
        except WatchlistUnavailableError as desktop_error:
            if primary_read is not None:
                return primary_read
            raise WatchlistUnavailableError(f"{primary_reason} Desktop fallback: {desktop_error}") from desktop_error
        return replace(desktop_read, error=primary_reason)
