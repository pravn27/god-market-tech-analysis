"""Pure indicator series calculated locally from normalized OHLCV candles.

Conventions follow TradingView Pine built-ins so values can be checked against the
user's charts: EMA is seeded with an SMA, RSI/ATR/DMI use Wilder (RMA) smoothing,
and Bollinger Bands use the population standard deviation. Every series has the same
length as its input; positions without enough history are ``None``.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from .models import Candle

Series = List[Optional[float]]


class InvalidCandlesError(ValueError):
    """Raised when candles cannot be used for any calculation."""


@dataclass(frozen=True)
class IndicatorProfile:
    """Versioned indicator settings; evidence conventions, not trading decisions."""

    version: str = "mtf-checklist-v1"
    ema_periods: tuple[int, ...] = (5, 13, 26, 50, 100, 150, 200)
    rsi_period: int = 14
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    bb_period: int = 20
    bb_stddev: float = 2.0
    dmi_period: int = 14
    adx_smoothing: int = 14
    stoch_k_period: int = 14
    stoch_k_smoothing: int = 3
    stoch_d_period: int = 3
    atr_period: int = 14


@dataclass(frozen=True)
class IndicatorSeries:
    profile: IndicatorProfile
    opens: List[float]
    highs: List[float]
    lows: List[float]
    closes: List[float]
    ema: Dict[int, Series] = field(default_factory=dict)
    rsi: Series = field(default_factory=list)
    macd_line: Series = field(default_factory=list)
    macd_signal: Series = field(default_factory=list)
    macd_hist: Series = field(default_factory=list)
    bb_upper: Series = field(default_factory=list)
    bb_basis: Series = field(default_factory=list)
    bb_lower: Series = field(default_factory=list)
    plus_di: Series = field(default_factory=list)
    minus_di: Series = field(default_factory=list)
    adx: Series = field(default_factory=list)
    stoch_k: Series = field(default_factory=list)
    stoch_d: Series = field(default_factory=list)
    atr: Series = field(default_factory=list)


def _require_period(period: int) -> None:
    if period < 1:
        raise ValueError("Indicator periods must be at least 1.")


def sma(values: Sequence[Optional[float]], period: int) -> Series:
    _require_period(period)
    out: Series = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        if any(v is None for v in window):
            continue
        out[i] = sum(window) / period  # type: ignore[arg-type]
    return out


def _smoothed(values: Sequence[Optional[float]], period: int, alpha: float) -> Series:
    """Exponential smoothing seeded with the SMA of the first ``period`` values."""
    out: Series = [None] * len(values)
    start = next((i for i, v in enumerate(values) if v is not None), None)
    if start is None or start + period > len(values):
        return out
    seed_window = values[start : start + period]
    if any(v is None for v in seed_window):
        return out
    previous = sum(seed_window) / period  # type: ignore[arg-type]
    out[start + period - 1] = previous
    for i in range(start + period, len(values)):
        value = values[i]
        if value is None:
            continue
        previous = alpha * value + (1 - alpha) * previous
        out[i] = previous
    return out


def ema(values: Sequence[Optional[float]], period: int) -> Series:
    _require_period(period)
    return _smoothed(values, period, 2 / (period + 1))


def rma(values: Sequence[Optional[float]], period: int) -> Series:
    _require_period(period)
    return _smoothed(values, period, 1 / period)


def rsi(closes: Sequence[float], period: int) -> Series:
    _require_period(period)
    gains: Series = [None]
    losses: Series = [None]
    for i in range(1, len(closes)):
        change = closes[i] - closes[i - 1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    avg_gain, avg_loss = rma(gains, period), rma(losses, period)
    out: Series = [None] * len(closes)
    for i, (gain, loss) in enumerate(zip(avg_gain, avg_loss)):
        if gain is None or loss is None:
            continue
        if loss == 0:
            out[i] = 100.0 if gain > 0 else 50.0
        else:
            out[i] = 100 - 100 / (1 + gain / loss)
    return out


def macd(closes: Sequence[float], fast: int, slow: int, signal: int) -> tuple[Series, Series, Series]:
    fast_ema, slow_ema = ema(closes, fast), ema(closes, slow)
    line: Series = [
        f - s if f is not None and s is not None else None for f, s in zip(fast_ema, slow_ema)
    ]
    signal_line = ema(line, signal)
    hist: Series = [
        m - s if m is not None and s is not None else None for m, s in zip(line, signal_line)
    ]
    return line, signal_line, hist


def bollinger_bands(closes: Sequence[float], period: int, stddev: float) -> tuple[Series, Series, Series]:
    basis = sma(closes, period)
    upper: Series = [None] * len(closes)
    lower: Series = [None] * len(closes)
    for i, mean in enumerate(basis):
        if mean is None:
            continue
        window = closes[i - period + 1 : i + 1]
        deviation = math.sqrt(sum((v - mean) ** 2 for v in window) / period)
        upper[i] = mean + stddev * deviation
        lower[i] = mean - stddev * deviation
    return upper, basis, lower


def stochastic(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    k_period: int,
    k_smoothing: int,
    d_period: int,
) -> tuple[Series, Series]:
    _require_period(k_period)
    raw: Series = [None] * len(closes)
    for i in range(k_period - 1, len(closes)):
        highest = max(highs[i - k_period + 1 : i + 1])
        lowest = min(lows[i - k_period + 1 : i + 1])
        if highest == lowest:
            continue
        raw[i] = 100 * (closes[i] - lowest) / (highest - lowest)
    k = sma(raw, k_smoothing)
    return k, sma(k, d_period)


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> List[float]:
    ranges = []
    for i in range(len(closes)):
        if i == 0:
            ranges.append(highs[0] - lows[0])
            continue
        previous_close = closes[i - 1]
        ranges.append(max(highs[i] - lows[i], abs(highs[i] - previous_close), abs(lows[i] - previous_close)))
    return ranges


def atr(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float], period: int) -> Series:
    return rma(true_range(highs, lows, closes), period)


def dmi(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int,
    adx_smoothing: int,
) -> tuple[Series, Series, Series]:
    n = len(closes)
    plus_dm: Series = [None] * n
    minus_dm: Series = [None] * n
    ranges: Series = [None] * n
    full_ranges = true_range(highs, lows, closes)
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > 0 else 0.0
        minus_dm[i] = down if down > up and down > 0 else 0.0
        ranges[i] = full_ranges[i]

    smoothed_tr = rma(ranges, period)
    smoothed_plus = rma(plus_dm, period)
    smoothed_minus = rma(minus_dm, period)
    plus_di: Series = [None] * n
    minus_di: Series = [None] * n
    dx: Series = [None] * n
    last_plus = last_minus = None
    for i in range(n):
        tr_value, p, m = smoothed_tr[i], smoothed_plus[i], smoothed_minus[i]
        if tr_value is None or p is None or m is None:
            continue
        if tr_value > 0:
            last_plus, last_minus = 100 * p / tr_value, 100 * m / tr_value
        if last_plus is None or last_minus is None:
            continue
        plus_di[i], minus_di[i] = last_plus, last_minus
        total = last_plus + last_minus
        dx[i] = abs(last_plus - last_minus) / (total if total != 0 else 1)
    adx = [100 * v if v is not None else None for v in rma(dx, adx_smoothing)]
    return plus_di, minus_di, adx


def candle_issue(candles: Sequence[Candle]) -> Optional[str]:
    """Explain why candles are unusable, or return ``None`` when they are valid."""
    if not candles:
        return "No candles were returned."
    previous_timestamp = None
    for candle in candles:
        prices = (candle.open, candle.high, candle.low, candle.close)
        if not all(math.isfinite(p) for p in prices):
            return f"Candle at {candle.timestamp.isoformat()} has non-finite prices."
        if candle.high < candle.low:
            return f"Candle at {candle.timestamp.isoformat()} has high below low."
        if previous_timestamp is not None and candle.timestamp <= previous_timestamp:
            return "Candles must be in strictly ascending timestamp order."
        previous_timestamp = candle.timestamp
    return None


def calculate_indicators(candles: Sequence[Candle], profile: IndicatorProfile) -> IndicatorSeries:
    issue = candle_issue(candles)
    if issue:
        raise InvalidCandlesError(issue)
    opens = [c.open for c in candles]
    highs = [c.high for c in candles]
    lows = [c.low for c in candles]
    closes = [c.close for c in candles]
    macd_line, macd_signal_line, macd_hist = macd(closes, profile.macd_fast, profile.macd_slow, profile.macd_signal)
    bb_upper, bb_basis, bb_lower = bollinger_bands(closes, profile.bb_period, profile.bb_stddev)
    plus_di, minus_di, adx_series = dmi(highs, lows, closes, profile.dmi_period, profile.adx_smoothing)
    stoch_k, stoch_d = stochastic(
        highs, lows, closes, profile.stoch_k_period, profile.stoch_k_smoothing, profile.stoch_d_period
    )
    return IndicatorSeries(
        profile=profile,
        opens=opens,
        highs=highs,
        lows=lows,
        closes=closes,
        ema={period: ema(closes, period) for period in profile.ema_periods},
        rsi=rsi(closes, profile.rsi_period),
        macd_line=macd_line,
        macd_signal=macd_signal_line,
        macd_hist=macd_hist,
        bb_upper=bb_upper,
        bb_basis=bb_basis,
        bb_lower=bb_lower,
        plus_di=plus_di,
        minus_di=minus_di,
        adx=adx_series,
        stoch_k=stoch_k,
        stoch_d=stoch_d,
        atr=atr(highs, lows, closes, profile.atr_period),
    )
