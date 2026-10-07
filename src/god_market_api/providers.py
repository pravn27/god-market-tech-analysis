"""Provider boundary for TradingView MCP sources.

The official MCP adapter obtains raw, source-owned facts and normalizes them
into ``ChartContext``. It never calculates signals or makes trading decisions.
"""

import json
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol, Sequence

from .models import Candle, ChartContext, DataSource, SourceHealth, SourceState, TechnicalSnapshot


class DataSourceUnavailableError(RuntimeError):
    """Raised when a source cannot provide fresh context for a request."""


class MCPToolCaller(Protocol):
    """Minimal boundary used by the provider and its contract tests."""

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


class ChartContextProvider(Protocol):
    async def health(self) -> SourceHealth:
        ...

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        ...


_TIMEFRAME_ALIASES = {
    "daily": "1D",
    "1d": "1D",
    "weekly": "1W",
    "1w": "1W",
    "monthly": "M",
    "1mo": "M",
    "month": "M",
}
_SUPPORTED_INTERVALS = {"1m", "5m", "15m", "30m", "1h", "4h", "1D", "1W", "M"}


def normalize_timeframe(timeframe: str) -> str:
    """Return the official-MCP interval while accepting dashboard-friendly labels."""
    value = timeframe.strip()
    normalized = _TIMEFRAME_ALIASES.get(value.lower(), value)
    if normalized not in _SUPPORTED_INTERVALS:
        raise DataSourceUnavailableError(
            f"Unsupported timeframe '{timeframe}'. Use one of: {', '.join(sorted(_SUPPORTED_INTERVALS))}."
        )
    return normalized


def technicals_interval(ohlcv_interval: str) -> str:
    """Map the OHLCV monthly code to the technicals tool's monthly code."""
    return "1M" if ohlcv_interval == "M" else ohlcv_interval


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    raise DataSourceUnavailableError("The official MCP returned an unexpected response shape.")


def _decode_tool_result(result: Any) -> Mapping[str, Any]:
    """Decode a direct test payload or the JSON text content of an MCP result."""
    if isinstance(result, Mapping):
        if result.get("isError") or result.get("is_error") or result.get("success") is False:
            raise DataSourceUnavailableError("The official MCP rejected the market-data request.")
        return result

    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        raise DataSourceUnavailableError("The official MCP rejected the market-data request.")

    structured_content = getattr(result, "structuredContent", None)
    if isinstance(structured_content, Mapping):
        return _decode_tool_result(structured_content)

    content: Sequence[Any] = getattr(result, "content", ())
    text = "".join(
        part for part in (getattr(item, "text", None) for item in content) if isinstance(part, str)
    ).strip()
    if not text:
        raise DataSourceUnavailableError("The official MCP returned no market-data payload.")
    try:
        return _as_mapping(json.loads(text))
    except json.JSONDecodeError as error:
        raise DataSourceUnavailableError("The official MCP returned a non-JSON market-data payload.") from error


def _payload_records(payload: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    for key in ("bars", "candles", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [record for record in value if isinstance(record, Mapping)]
        if isinstance(value, Mapping):
            nested = _payload_records(value)
            if nested:
                return nested
    return []


def _timestamp(value: Any) -> datetime:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
        except ValueError as error:
            raise DataSourceUnavailableError("The official MCP returned an invalid candle timestamp.") from error
    raise DataSourceUnavailableError("The official MCP returned a candle without a timestamp.")


def _candles(payload: Mapping[str, Any]) -> list[Candle]:
    parsed: list[Candle] = []
    for bar in _payload_records(payload):
        try:
            volume_value = bar.get("volume")
            if volume_value is None:
                volume_value = bar.get("v")
            parsed.append(
                Candle(
                    timestamp=_timestamp(bar.get("timestamp", bar.get("time", bar.get("t")))),
                    open=float(bar["open"] if "open" in bar else bar["o"]),
                    high=float(bar["high"] if "high" in bar else bar["h"]),
                    low=float(bar["low"] if "low" in bar else bar["l"]),
                    close=float(bar["close"] if "close" in bar else bar["c"]),
                    volume=float(volume_value) if volume_value is not None else None,
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise DataSourceUnavailableError("The official MCP returned an invalid OHLCV candle.") from error
    if not parsed:
        raise DataSourceUnavailableError("The official MCP returned no OHLCV candles.")
    return sorted(parsed, key=lambda candle: candle.timestamp)


def _technical_snapshot(payload: Mapping[str, Any]) -> TechnicalSnapshot:
    summary = payload.get("summary")
    summary_text = summary if isinstance(summary, str) else None
    summary_values = summary if isinstance(summary, Mapping) else {}
    values = payload.get("values", {})
    numeric_values = (
        {
            str(key): float(value)
            for key, value in values.items()
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        if isinstance(values, Mapping)
        else {}
    )
    return TechnicalSnapshot(
        recommendation=payload.get("recommendation") or summary_values.get("RECOMMENDATION"),
        summary=summary_text or summary_values.get("RECOMMENDATION"),
        moving_averages=payload.get("moving_averages") or payload.get("movingAverages"),
        oscillators=payload.get("oscillators"),
        values=numeric_values,
    )


class OfficialMCPProvider:
    """Primary, read-only adapter for the TradingView official MCP.

    ``tool_caller`` is normally the application-owned OAuth coordinator. It is
    injected in tests so the response contract can be verified without a live
    TradingView session.
    """

    def __init__(self, tool_caller: MCPToolCaller | None = None, candle_count: int = 500) -> None:
        self._tool_caller = tool_caller
        self._candle_count = candle_count
        self._last_success_at: datetime | None = None

    async def health(self) -> SourceHealth:
        if self._tool_caller is None:
            return SourceHealth(
                source=DataSource.OFFICIAL_MCP,
                state=SourceState.NOT_CONFIGURED,
                detail="Official MCP application authorization has not been configured for this service.",
                checked_at=datetime.now(timezone.utc),
            )
        authorization_check = getattr(self._tool_caller, "is_authenticated", None)
        if authorization_check is not None and not await authorization_check():
            return SourceHealth(
                source=DataSource.OFFICIAL_MCP,
                state=SourceState.NOT_CONFIGURED,
                detail="Official MCP application authorization has not been completed for this service.",
                checked_at=datetime.now(timezone.utc),
            )
        return SourceHealth(
            source=DataSource.OFFICIAL_MCP,
            state=SourceState.READY if self._last_success_at else SourceState.NOT_CONFIGURED,
            detail=(
                "Official MCP adapter is ready."
                if self._last_success_at
                else "Official MCP adapter is configured but has not completed a market-data request."
            ),
            checked_at=datetime.now(timezone.utc),
            last_success_at=self._last_success_at,
        )

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        context = await self.get_price_context(symbol, timeframe, candle_count=self._candle_count)
        technicals = None
        warnings: list[str] = []
        try:
            technical_result = await self._tool_caller.call_tool(
                "mcp-tv-get-technicals-rating",
                {"symbol": symbol, "interval": technicals_interval(context.timeframe)},
            )
            technicals = _technical_snapshot(_decode_tool_result(technical_result))
        except Exception:
            warnings.append("The official technical snapshot is temporarily unavailable; OHLCV context is still current.")
        return context.model_copy(update={"technicals": technicals, "warnings": warnings})

    async def get_price_context(
        self, symbol: str, timeframe: str, *, candle_count: int = 2
    ) -> ChartContext:
        """Return normalized OHLCV only for breadth and performance calculations."""
        if self._tool_caller is None:
            raise DataSourceUnavailableError(
                "Official TradingView MCP is not configured for the local service. No chart context was returned."
            )
        if candle_count < 1:
            raise ValueError("candle_count must be at least 1.")

        interval = normalize_timeframe(timeframe)
        try:
            ohlcv_result = await self._tool_caller.call_tool(
                "mcp-tv-get-ohlcv", {"symbol": symbol, "interval": interval, "count": candle_count}
            )
        except DataSourceUnavailableError:
            raise
        except Exception as error:
            raise DataSourceUnavailableError(
                "The official MCP market-data request could not be completed. No chart context was returned."
            ) from error

        candles = _candles(_decode_tool_result(ohlcv_result))
        source_timestamp = candles[-1].timestamp
        self._last_success_at = datetime.now(timezone.utc)
        return ChartContext(
            symbol=symbol,
            timeframe=interval,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=source_timestamp,
            freshness_state=SourceState.READY,
            candles=candles,
        )
