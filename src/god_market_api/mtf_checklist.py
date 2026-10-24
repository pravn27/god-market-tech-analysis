"""PAPA + SMM multi-timeframe checklist rules (profile ``mtf-checklist-v1``).

Each rule turns local indicator/price-structure evidence into the wording of the
user's worksheet. Rules are pure functions over plain series so every row of the
specification's rule tables can be tested directly.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Sequence

from .models import Bias, Candle, ChecklistCell
from .significant_candles import significant_candle_evidence
from .price_structure import (
    LocationKind,
    Pivot,
    SwingPoint,
    analyze_dow_structure_v2,
    detect_candle_patterns,
    dow_trend,
    find_pivots,
    locate_price,
    price_action,
)
from .technical_indicators import (
    IndicatorProfile,
    IndicatorSeries,
    InvalidCandlesError,
    calculate_indicators,
)

Series = Sequence[Optional[float]]


@dataclass(frozen=True)
class ChecklistThresholds:
    """Configurable thresholds; defaults are recorded in the specification."""

    indicators: IndicatorProfile = field(default_factory=IndicatorProfile)
    pivot_window: int = 5
    recent_crossover_periods: int = 3
    slope_lookback: int = 3
    rsi_near_50_low: float = 45.0
    rsi_near_50_high: float = 55.0
    bb_near_median_fraction: float = 0.10
    bb_flat_tolerance: float = 0.005
    ema_flat_tolerance: float = 0.005
    ema_steep_tolerance: float = 0.015
    sr_proximity_atr: float = 1.0
    macd_near_zero_fraction: float = 0.10
    macd_zero_range_window: int = 50
    wick_tolerance: float = 0.02
    dow_significance_atr: float = 0.5
    divergence_lookback: int = 40
    # Bars after a swing before it counts for divergence (the Dow pivot window stays at pivot_window).
    divergence_confirm_bars: int = 2
    volume_average_period: int = 20
    volume_near_average_band: float = 0.2
    volume_double_ratio: float = 2.0
    fib_tolerance: float = 0.03
    pattern_lookback: int = 60
    double_top_tolerance: float = 0.015
    double_top_min_gap: int = 10

    @property
    def version(self) -> str:
        return self.indicators.version


@dataclass(frozen=True)
class ChecklistRow:
    id: str
    section: str
    label: str
    automated: bool


SECTION_CONTEXT = "1. Overall Context / Viewbuilding / Dow Theory"
SECTION_PRICE_ACTION = "2. Dow Theory Advanced + Price Action + Candlestick Pattern"
SECTION_INDICATORS = "3. Check Indicators"
SECTION_SETUPS = "5. Concepts / Setups / Confirmation"

CHECKLIST_ROWS: tuple[ChecklistRow, ...] = (
    ChecklistRow("dow_trend", SECTION_CONTEXT, "Dow Theory", True),
    ChecklistRow("dow_structure_v2", SECTION_CONTEXT, "Dow structure v2 (closed candles)", True),
    ChecklistRow("location", SECTION_CONTEXT, "Where do you stand in overall trend / context?", True),
    ChecklistRow("support_resistance", SECTION_CONTEXT, "Support / Resistance (horizontal swing levels)", True),
    ChecklistRow("trendlines", SECTION_CONTEXT, "Angular trendlines", False),
    ChecklistRow("significant_candles", SECTION_CONTEXT, "Mark significant & event candles", False),
    ChecklistRow("price_action", SECTION_PRICE_ACTION, "Current candle OPEN / CLOSE vs previous candle OHLC", True),
    ChecklistRow("heikin_ashi", SECTION_PRICE_ACTION, "Heikin-Ashi candle", True),
    ChecklistRow("candlestick_pattern", SECTION_PRICE_ACTION, "Candlestick pattern", True),
    ChecklistRow("significant_candle", SECTION_PRICE_ACTION, "Significant candle", True),
    ChecklistRow("special_candles", SECTION_PRICE_ACTION, "Special candles near / at support & resistance", True),
    ChecklistRow("bollinger", SECTION_INDICATORS, "Bollinger Band", True),
    ChecklistRow("rsi", SECTION_INDICATORS, "RSI", True),
    ChecklistRow("dmi", SECTION_INDICATORS, "DMI", True),
    ChecklistRow("adx", SECTION_INDICATORS, "ADX", True),
    ChecklistRow("macd", SECTION_INDICATORS, "MACD", True),
    ChecklistRow("stochastic", SECTION_INDICATORS, "Stochastic", True),
    ChecklistRow("emas", SECTION_INDICATORS, "EMAs", True),
    ChecklistRow("divergence", SECTION_INDICATORS, "Divergence (RSI, MACD, Stochastic %K)", True),
    ChecklistRow("chart_pattern", SECTION_SETUPS, "Concepts / Setups / Chart Patterns", True),
    ChecklistRow("weapon_candle", SECTION_SETUPS, "Significant / Weapon / Confirmation candle", False),
    ChecklistRow("weapon_volume", SECTION_SETUPS, "Volume of weapon candle", True),
    ChecklistRow("setup_type", SECTION_SETUPS, "Momentum or Swing setup", False),
    ChecklistRow("followup", SECTION_SETUPS, "Do you have follow-up candles?", False),
    ChecklistRow("what_if", SECTION_SETUPS, "Be ready with What If analysis", False),
)


@dataclass(frozen=True)
class TimeframeEvaluation:
    cells: Dict[str, ChecklistCell]
    series: Optional[IndicatorSeries] = None
    last_close: Optional[float] = None
    last_candle_at: Optional[datetime] = None
    unavailable_reason: Optional[str] = None


def _unavailable(reason: str, rule_id: str) -> ChecklistCell:
    return ChecklistCell(bias=Bias.UNAVAILABLE, rule_ids=[rule_id], unavailable_reason=reason)


def _needs(period: int) -> str:
    return f"Needs about {period} candles for this indicator."


def _at(series: Series, offset: int = 0) -> Optional[float]:
    index = len(series) - 1 - offset
    return series[index] if 0 <= index < len(series) else None


def _recent_cross(a: Series, b: Series, periods: int) -> Optional[tuple[str, int]]:
    """Most recent crossover of ``a`` over ``b`` within the last ``periods`` candles."""
    for offset in range(periods):
        i = len(a) - 1 - offset
        if i < 1:
            break
        prev_a, prev_b, cur_a, cur_b = a[i - 1], b[i - 1], a[i], b[i]
        if None in (prev_a, prev_b, cur_a, cur_b):
            continue
        if prev_a <= prev_b and cur_a > cur_b:
            return "up", i
        if prev_a >= prev_b and cur_a < cur_b:
            return "down", i
    return None


def _level_cross(series: Series, level: float, periods: int) -> Optional[str]:
    return (_recent_cross(series, [level] * len(series), periods) or (None, 0))[0]


def _round(value: Optional[float], digits: int = 4) -> Optional[float]:
    return round(value, digits) if value is not None else None


# Indicators


def bollinger_cell(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    upper: Series,
    basis: Series,
    lower: Series,
    t: ChecklistThresholds,
    *,
    forming: bool = False,
) -> ChecklistCell:
    """Bollinger state. Touch and band-direction tests use the signal candle: the last closed candle
    when ``forming`` is true (the latest candle is still changing), otherwise the latest candle."""
    rule = "bb"
    u, m, l = _at(upper), _at(basis), _at(lower)
    lookback = t.slope_lookback
    u_prev, l_prev = _at(upper, lookback), _at(lower, lookback)
    shift = 1 if forming else 0
    signal = len(upper) - 1 - shift
    if None in (u, m, l, u_prev, l_prev) or signal - lookback < 0:
        return _unavailable(_needs(t.indicators.bb_period + lookback + shift), rule)
    if upper[signal] is None or lower[signal] is None or upper[signal - lookback] is None or lower[signal - lookback] is None:
        return _unavailable(_needs(t.indicators.bb_period + lookback + shift), rule)

    def change(now: float, before: float) -> float:
        return (now - before) / abs(before) if before else 0.0

    s_upper, s_lower = upper[signal], lower[signal]
    s_upper_prev, s_lower_prev = upper[signal - lookback], lower[signal - lookback]
    upper_expanding = change(s_upper, s_upper_prev) > t.bb_flat_tolerance
    lower_expanding = -change(s_lower, s_lower_prev) > t.bb_flat_tolerance
    upper_flat = abs(change(s_upper, s_upper_prev)) <= t.bb_flat_tolerance
    lower_flat = abs(change(s_lower, s_lower_prev)) <= t.bb_flat_tolerance
    recent = range(t.recent_crossover_periods)
    upper_touched = any(
        upper[signal - k] is not None and highs[signal - k] >= upper[signal - k] for k in recent
    )
    lower_touched = any(
        lower[signal - k] is not None and lows[signal - k] <= lower[signal - k] for k in recent
    )
    close, width = closes[-1], u - l

    if highs[signal] >= s_upper and upper_expanding:
        labels, bias, rule = ["UBBC, BB Expands"], Bias.BULLISH, "bb.ubbc"
    elif lows[signal] <= s_lower and lower_expanding:
        labels, bias, rule = ["LBBC, BB Expands"], Bias.BEARISH, "bb.lbbc"
    elif upper_touched and upper_flat:
        labels, bias, rule = ["UBBC Failure, BKT"], Bias.BEARISH, "bb.bkt"
    elif lower_touched and lower_flat:
        labels, bias, rule = ["LBBC Failure, BKP"], Bias.BULLISH, "bb.bkp"
    elif abs(close - m) <= t.bb_near_median_fraction * width:
        labels, bias, rule = ["Price is Near Median"], Bias.NEUTRAL, "bb.median"
    elif close > m:
        labels, bias, rule = ["Price is Above Median"], Bias.BULLISH, "bb.median"
    else:
        labels, bias, rule = ["Price is Below Median"], Bias.BEARISH, "bb.median"

    # Total width is judged on the latest candle; each side is judged on the signal candle.
    width_prev = u_prev - l_prev
    latest_upper_flat = abs(change(u, u_prev)) <= t.bb_flat_tolerance
    latest_lower_flat = abs(change(l, l_prev)) <= t.bb_flat_tolerance
    if latest_upper_flat and latest_lower_flat:
        labels.append("Bands are Flat")
    elif width_prev and width > width_prev * (1 + t.bb_flat_tolerance):
        labels.append("Bands Expanding")
    elif width_prev and width < width_prev * (1 - t.bb_flat_tolerance):
        labels.append("Bands Contracting")
    else:
        labels.append("Bands are Flat")

    def side_state(expanding: bool, flat: bool) -> str:
        return "expanding" if expanding else "flat" if flat else "contracting"

    labels.append(f"Upper band {side_state(upper_expanding, upper_flat)}")
    labels.append(f"Lower band {side_state(lower_expanding, lower_flat)}")
    if forming:
        if highs[-1] >= u:
            labels.append("Forming candle touches UBB")
        if lows[-1] <= l:
            labels.append("Forming candle touches LBB")

    # The configured stddev multiple gives one standard deviation; three SD bands scale from it.
    band_3sd = 3 * (u - m) / t.indicators.bb_stddev
    if highs[-1] >= m + band_3sd:
        labels.append("Beyond +3 SD band")
    elif lows[-1] <= m - band_3sd:
        labels.append("Beyond -3 SD band")

    return ChecklistCell(
        labels=labels,
        bias=bias,
        values={
            "upper": _round(u),
            "basis": _round(m),
            "lower": _round(l),
            "width": _round(width),
            "percent_b": _round((close - l) / width if width else None),
        },
        rule_ids=[rule],
    )


def rsi_cell(rsi: Series, t: ChecklistThresholds) -> ChecklistCell:
    value = _at(rsi)
    if value is None:
        return _unavailable(_needs(t.indicators.rsi_period + 1), "rsi")
    if value > 80:
        label, bias = "> 80, Unsustainable for Bulls", Bias.BULLISH
    elif value > 60:
        label, bias = "> 60, Bullish Momentum", Bias.BULLISH
    elif value < 20:
        label, bias = "< 20, Unsustainable for Bears", Bias.BEARISH
    elif value < 40:
        label, bias = "< 40, Bearish Momentum", Bias.BEARISH
    elif t.rsi_near_50_low <= value <= t.rsi_near_50_high:
        label, bias = "Near 50", Bias.NEUTRAL
    else:
        label = f"Swing zone (40 - 60), {'Above' if value > 50 else 'Below'} 50"
        bias = Bias.NEUTRAL
    labels = [label, f"RSI {value:.2f}"]
    periods = t.recent_crossover_periods
    for level, direction, text in (
        (60, "up", "Crossing above 60"),
        (40, "down", "Crossing below 40"),
        (40, "up", "Crossing above 40"),
        (60, "down", "Crossing below 60"),
    ):
        if _level_cross(rsi, level, periods) == direction:
            labels.append(text)
    return ChecklistCell(
        labels=labels, bias=bias, values={"rsi": _round(value, 2), "rsi_prev": _round(_at(rsi, 1), 2)}, rule_ids=["rsi"]
    )


def dmi_cell(plus_di: Series, minus_di: Series, t: ChecklistThresholds) -> ChecklistCell:
    plus, minus = _at(plus_di), _at(minus_di)
    plus_prev, minus_prev = _at(plus_di, t.slope_lookback), _at(minus_di, t.slope_lookback)
    if None in (plus, minus):
        return _unavailable(_needs(t.indicators.dmi_period + 1), "dmi")
    if plus > minus:
        labels, bias = ["+DI > -DI"], Bias.BULLISH
    elif minus > plus:
        labels, bias = ["-DI > +DI"], Bias.BEARISH
    else:
        labels, bias = ["+DI = -DI"], Bias.NEUTRAL
    if plus_prev is not None and minus_prev is not None:
        spread, spread_prev = abs(plus - minus), abs(plus_prev - minus_prev)
        if spread < spread_prev:
            labels.append("Contracting")
        elif spread > spread_prev:
            labels.append("Expanding")
    cross = _recent_cross(plus_di, minus_di, t.recent_crossover_periods)
    if cross:
        labels.append("PCO" if cross[0] == "up" else "NCO")
    return ChecklistCell(
        labels=labels,
        bias=bias,
        values={"plus_di": _round(plus, 2), "minus_di": _round(minus, 2)},
        rule_ids=["dmi"],
    )


def adx_cell(adx: Series, plus_di: Series, minus_di: Series, t: ChecklistThresholds) -> ChecklistCell:
    value, previous = _at(adx), _at(adx, t.slope_lookback)
    if value is None:
        return _unavailable(_needs(t.indicators.dmi_period + t.indicators.adx_smoothing), "adx")
    rising = previous is not None and value > previous
    falling = previous is not None and value < previous
    labels: List[str] = []
    if rising and value >= 12:
        labels.append("Raising > 12 (Gaining good strength in Trend)")
    elif rising:
        labels.append("Raising")
    elif falling:
        labels.append("Falling (Losing strength in Trend)")
    if value > 55:
        labels.append("Unsustainable (> 55)")
    elif value > 14:
        labels.append("Excellent Momentum (> 14)")
    elif value >= 12:
        labels.append("Good Momentum (12 - 14)")
    elif value >= 10:
        labels.append("Momentum Building (10 - 12)")
    else:
        labels.append("No Momentum (< 10)")

    labels.append(f"ADX {value:.2f}")
    bias = Bias.NEUTRAL
    plus, minus = _at(plus_di), _at(minus_di)
    if rising and value >= 12 and plus is not None and minus is not None and plus != minus:
        bias = Bias.BULLISH if plus > minus else Bias.BEARISH
    return ChecklistCell(
        labels=labels, bias=bias, values={"adx": _round(value, 2), "adx_prev": _round(previous, 2)}, rule_ids=["adx"]
    )


def _macd_position(line: Series, t: ChecklistThresholds) -> str:
    recent = [abs(v) for v in line[-t.macd_zero_range_window :] if v is not None]
    value = _at(line)
    if recent and abs(value) <= t.macd_near_zero_fraction * max(recent):
        return "near Zero Line"
    return "above Zero Line" if value > 0 else "below Zero Line"


def _tick(series: Series) -> Optional[str]:
    now, before = _at(series), _at(series, 1)
    if now is None or before is None:
        return None
    if now > before:
        return "up"
    if now < before:
        return "down"
    return "flat"


def macd_cell(line: Series, signal: Series, t: ChecklistThresholds) -> ChecklistCell:
    value, signal_value = _at(line), _at(signal)
    if value is None or signal_value is None:
        profile = t.indicators
        return _unavailable(_needs(profile.macd_slow + profile.macd_signal), "macd")
    state = "PCO" if value > signal_value else "NCO" if value < signal_value else None
    tick = _tick(line)
    cross = _recent_cross(line, signal, t.recent_crossover_periods)
    position = _macd_position(line, t)

    if cross and cross[0] == "up":
        headline, bias = f"(PCO) Buy Signal {position}", Bias.BULLISH
    elif cross and cross[0] == "down":
        headline, bias = f"(NCO) Sell Signal {position}", Bias.BEARISH
    elif state == "PCO" and tick == "up":
        headline, bias = f"Buy Signal {position}", Bias.BULLISH
    elif state == "NCO" and tick == "down":
        headline, bias = f"Sell Signal {position}", Bias.BEARISH
    else:
        headline, bias = f"Not Clear {position}", Bias.NEUTRAL

    labels = [headline]
    if state:
        labels.append(f"{state} state")
    if tick in ("up", "down"):
        labels.append("Up Tick" if tick == "up" else "Down Tick")
    elif tick == "flat":
        labels.append("Flat")
    return ChecklistCell(
        labels=labels,
        bias=bias,
        values={
            "macd": _round(value),
            "signal": _round(signal_value),
            "histogram": _round(value - signal_value),
        },
        rule_ids=["macd"],
    )


def stochastic_cell(k: Series, d: Series, t: ChecklistThresholds) -> ChecklistCell:
    k_value, d_value = _at(k), _at(d)
    if k_value is None or d_value is None:
        profile = t.indicators
        return _unavailable(_needs(profile.stoch_k_period + profile.stoch_k_smoothing + profile.stoch_d_period), "stoch")
    tick = _tick(k)
    cross = _recent_cross(k, d, t.recent_crossover_periods)
    if k_value > 80:
        zone = "(> 80)"
    elif k_value < 20:
        zone = "(< 20)"
    elif k_value >= 70:
        zone = "(Near 80)"
    elif k_value <= 30:
        zone = "(Near 20)"
    else:
        zone = ""

    if cross and cross[0] == "up":
        bias = Bias.BULLISH
        if k_value < 20:
            headline = "(< 20) Buy Signal from OverSold (10 - 20)"
        else:
            headline = " ".join(p for p in (zone, "PCO Buy Signal", "Up tick" if tick == "up" else "") if p)
    elif cross and cross[0] == "down":
        bias = Bias.BEARISH
        if k_value > 80:
            headline = "(> 80) NCO Sell Signal from OverBought (80 - 90)"
        else:
            headline = " ".join(p for p in (zone, "NCO Sell Signal", "Down tick" if tick == "down" else "") if p)
    else:
        bias = Bias.NEUTRAL
        headline = "Overbought (> 80)" if k_value > 80 else "Oversold (< 20)" if k_value < 20 else "Not Clear"

    labels = [headline, f"%K {k_value:.2f} / %D {d_value:.2f}"]
    if not cross and tick in ("up", "down"):
        labels.append("Up tick" if tick == "up" else "Down tick")
    labels.append("PCO state" if k_value > d_value else "NCO state" if k_value < d_value else "K = D")
    return ChecklistCell(
        labels=labels, bias=bias, values={"k": _round(k_value, 2), "d": _round(d_value, 2)}, rule_ids=["stoch"]
    )


def _ema_slope(series: Series, t: ChecklistThresholds) -> Optional[float]:
    """Fractional change of an EMA over ``slope_lookback`` candles; None when unavailable."""
    now, before = _at(series), _at(series, t.slope_lookback)
    if now is None or before is None or before == 0:
        return None
    return (now - before) / abs(before)


EMA_TREND_PERIODS = (5, 13, 26, 50, 100, 150, 200)

_EMA_TREND_LABELS = {
    "flat": "Flat EMAs",
    "up": "Upward EMAs",
    "down": "Downward EMAs",
    "steep_up": "Steep upward EMAs",
    "steep_down": "Steep downward EMAs",
}


def _ema_trend(slope: float, t: ChecklistThresholds) -> str:
    """Classify one EMA line by its slope over ``slope_lookback`` candles."""
    if abs(slope) <= t.ema_flat_tolerance:
        return "flat"
    if slope >= t.ema_steep_tolerance:
        return "steep_up"
    if slope <= -t.ema_steep_tolerance:
        return "steep_down"
    return "up" if slope > 0 else "down"


def _ema_trend_labels(trends: Mapping[int, str]) -> List[str]:
    """Group EMA periods by trend, e.g. ``Flat EMAs: 5, 13, 26``."""
    labels = []
    for trend, name in _EMA_TREND_LABELS.items():
        periods = [str(period) for period, value in trends.items() if value == trend]
        if periods:
            labels.append(f"{name}: {', '.join(periods)}")
    return labels


def ema_cell(closes: Sequence[float], emas: Mapping[int, Series], t: ChecklistThresholds) -> ChecklistCell:
    close = closes[-1]
    latest = {period: _at(series) for period, series in emas.items()}
    required = (5, 13, 26, 50)
    if any(latest.get(p) is None for p in required):
        return _unavailable(_needs(50), "ema")
    labels = [
        f"Price {'>' if close > latest[p] else '<'} {p}"
        for p in t.indicators.ema_periods
        if latest.get(p) is not None
    ]
    e5, e13, e26 = (latest[p] for p in (5, 13, 26))
    poc = e5 > e13 > e26
    noc = e5 < e13 < e26
    if poc:
        labels.append("POC, 5 > 13 > 26")
    elif noc:
        labels.append("NOC, 5 < 13 < 26")
    else:
        labels.append("EMAs intermingled")
    slopes = {p: _ema_slope(emas[p], t) for p in EMA_TREND_PERIODS if p in emas}
    trends = {p: _ema_trend(s, t) for p, s in slopes.items() if s is not None}
    labels.extend(_ema_trend_labels(trends))
    e100, e150, e200 = latest.get(100), latest.get(150), latest.get(200)
    if None not in (e100, e150, e200):
        if e100 > e150 > e200:
            labels.append("POC, 100 > 150 > 200")
        elif e100 < e150 < e200:
            labels.append("NOC, 100 < 150 < 200")
    e5_long, e50 = latest.get(5), latest.get(50)
    if None not in (e5_long, e50, e100, e200):
        # 5 > 50 > 100 with 50 > 200 implies every required pair (5 > 100, 5 > 200) as well.
        if e5_long > e50 > e100 and e50 > e200:
            labels.append("POC, 5 > 50 > 100 and 50 > 200")
        elif e5_long < e50 < e100 and e50 < e200:
            labels.append("NOC, 5 < 50 < 100 and 50 < 200")
    for slow in (13, 26):
        cross = _recent_cross(emas[5], emas[slow], t.recent_crossover_periods)
        if cross:
            labels.append(f"5 EMA {'PCO' if cross[0] == 'up' else 'NCO'} with {slow} EMA")

    # Colour follows the PCO / NCO state of the 5 > 13 > 26 stack; intermingled lines stay neutral.
    bias = Bias.BULLISH if poc else Bias.BEARISH if noc else Bias.NEUTRAL
    values = {f"ema_{p}": _round(latest.get(p)) for p in t.indicators.ema_periods}
    values["close"] = _round(close)
    for p in EMA_TREND_PERIODS:
        slope = slopes.get(p)
        values[f"ema_{p}_slope_pct"] = _round(slope * 100, 2) if slope is not None else None
        values[f"ema_{p}_trend"] = trends.get(p)
    return ChecklistCell(labels=labels, bias=bias, values=values, rule_ids=["ema"])


# Evidence added inside existing rows (divergence, volume, breakouts, Fibonacci, chart patterns)

FIB_LEVELS = (0.236, 0.382, 0.5, 0.618, 0.786)


def _with_labels(cell: ChecklistCell, extra: Sequence[str], rule_id: str) -> ChecklistCell:
    """Append evidence labels to an existing row cell; the cell's bias is left unchanged."""
    if cell.bias is Bias.UNAVAILABLE or not extra:
        return cell
    return cell.model_copy(update={"labels": [*cell.labels, *extra], "rule_ids": [*cell.rule_ids, rule_id]})


def _divergence_labels(
    name: str, highs: Sequence[Pivot], lows: Sequence[Pivot], oscillator: Series, count: int, t: ChecklistThresholds
) -> List[str]:
    """Price swing vs oscillator swing over the last two confirmed pivots, when the latest is recent."""
    recent_from = count - t.divergence_lookback
    labels: List[str] = []
    if len(highs) >= 2 and highs[-1].index >= recent_from:
        before, latest = highs[-2], highs[-1]
        o_before, o_latest = oscillator[before.index], oscillator[latest.index]
        if None not in (o_before, o_latest) and latest.price > before.price and o_latest < o_before:
            labels.append(f"Bearish divergence ({name})")
    if len(lows) >= 2 and lows[-1].index >= recent_from:
        before, latest = lows[-2], lows[-1]
        o_before, o_latest = oscillator[before.index], oscillator[latest.index]
        if None not in (o_before, o_latest) and latest.price < before.price and o_latest > o_before:
            labels.append(f"Bullish divergence ({name})")
    return labels


def divergence_pivots(
    highs: Sequence[float], lows: Sequence[float], t: ChecklistThresholds
) -> tuple[List[Pivot], List[Pivot]]:
    """Swing points for divergence: same left side as Dow, confirmed after fewer bars so the latest top is seen."""
    return find_pivots(highs, lows, t.pivot_window, t.divergence_confirm_bars)


def divergence_cell(
    oscillators: Sequence[tuple[str, Series]],
    highs: Sequence[Pivot],
    lows: Sequence[Pivot],
    count: int,
    t: ChecklistThresholds,
) -> ChecklistCell:
    """Divergence row: each oscillator's labels in one cell. Neutral bias, a warning to read with the other rows."""
    if len(highs) < 2 and len(lows) < 2:
        return _unavailable("Needs two confirmed swing highs or lows.", "divergence")
    labels: List[str] = []
    for name, oscillator in oscillators:
        labels.extend(_divergence_labels(name, highs, lows, oscillator, count, t))
    if not labels:
        labels = ["No divergence (RSI, MACD, Stochastic %K)"]
    return ChecklistCell(labels=labels, bias=Bias.NEUTRAL, rule_ids=["divergence"])


def volume_cell(candles: Sequence[Candle], t: ChecklistThresholds) -> ChecklistCell:
    """Latest closed candle volume against the average of the preceding candles."""
    rule = "volume"
    period = t.volume_average_period
    if len(candles) < period + 1:
        return _unavailable(_needs(period + 1), rule)
    prior, current = candles[-period - 1 : -1], candles[-1]
    if current.volume is None or any(c.volume is None for c in prior):
        return _unavailable("Volume is not provided for this timeframe.", rule)
    average = sum(c.volume for c in prior) / period
    if average <= 0:
        return _unavailable("Average volume is zero.", rule)
    ratio = current.volume / average
    if ratio < 1 - t.volume_near_average_band:
        label = "Less than average volume"
    elif ratio <= 1 + t.volume_near_average_band:
        label = "Average volume"
    elif ratio < t.volume_double_ratio:
        label = "More than average volume"
    else:
        label = "Double average volume (high)"
    return ChecklistCell(
        labels=[label, f"{ratio:.2f}x the {period}-candle average"],
        bias=Bias.NEUTRAL,
        values={
            "volume": _round(current.volume, 2),
            "average_volume": _round(average, 2),
            "volume_ratio": _round(ratio, 2),
        },
        rule_ids=[rule],
    )


def _breakout_labels(
    candles: Sequence[Candle],
    highs: Sequence[Pivot],
    lows: Sequence[Pivot],
    volume_ratio: Optional[float],
    t: ChecklistThresholds,
) -> List[str]:
    """Latest closed candle crossing a confirmed swing level (prior close on one side, close on the other)."""
    if len(candles) < 2:
        return []
    latest_index = len(candles) - 1
    previous_close, close = candles[-2].close, candles[-1].close
    volume_note = ""
    if volume_ratio is not None:
        volume_note = (
            ", volume confirms" if volume_ratio >= 1 + t.volume_near_average_band else ", volume does not confirm"
        )
    for pivot in reversed([p for p in highs if p.index < latest_index]):
        if previous_close <= pivot.price < close:
            return [f"Breakout above {pivot.price:,.2f}{volume_note}"]
    for pivot in reversed([p for p in lows if p.index < latest_index]):
        if previous_close >= pivot.price > close:
            return [f"Breakdown below {pivot.price:,.2f}{volume_note}"]
    return []


def _fibonacci_labels(
    candles: Sequence[Candle],
    swing_highs: Sequence[SwingPoint],
    swing_lows: Sequence[SwingPoint],
    t: ChecklistThresholds,
) -> List[str]:
    """Where the latest close sits inside the most recent swing leg (retracement of that leg)."""
    if not candles or not swing_highs or not swing_lows:
        return []
    high, low = swing_highs[-1], swing_lows[-1]
    span = high.price - low.price
    if span <= 0:
        return []
    close = candles[-1].close
    if high.index > low.index:
        retrace, leg = (high.price - close) / span, "up-leg pullback"
    else:
        retrace, leg = (close - low.price) / span, "down-leg bounce"
    if not 0 <= retrace <= 1:
        return ["Close outside the latest swing leg (no Fibonacci zone)"]
    nearest = min(FIB_LEVELS, key=lambda level: abs(level - retrace))
    note = f", near {nearest * 100:.1f}%" if abs(nearest - retrace) <= t.fib_tolerance else ""
    return [f"Fib {retrace * 100:.1f}% of {leg}{note}"]


def chart_pattern_cell(
    candles: Sequence[Candle], highs: Sequence[Pivot], lows: Sequence[Pivot], t: ChecklistThresholds
) -> ChecklistCell:
    """Double top / double bottom from the last two confirmed swing pivots; the neckline break is the trigger."""
    rule = "chart-pattern"
    if not candles:
        return _unavailable("No closed candles are available.", rule)
    start, close = len(candles) - t.pattern_lookback, candles[-1].close
    labels: List[str] = []
    bias = Bias.NEUTRAL
    recent_highs = [p for p in highs if p.index >= start]
    if len(recent_highs) >= 2:
        first, second = recent_highs[-2], recent_highs[-1]
        peak = max(first.price, second.price)
        if (
            second.index - first.index >= t.double_top_min_gap
            and abs(second.price - first.price) / peak <= t.double_top_tolerance
        ):
            neckline = min(c.low for c in candles[first.index : second.index + 1])
            if (peak - neckline) / peak >= t.double_top_tolerance:
                if close < neckline:
                    labels.append(f"Double Top, neckline {neckline:,.2f} broken")
                    bias = Bias.BEARISH
                else:
                    labels.append(f"Double Top candidate, neckline {neckline:,.2f} holding")
    recent_lows = [p for p in lows if p.index >= start]
    if not labels and len(recent_lows) >= 2:
        first, second = recent_lows[-2], recent_lows[-1]
        trough = min(first.price, second.price)
        if (
            second.index - first.index >= t.double_top_min_gap
            and abs(second.price - first.price) / trough <= t.double_top_tolerance
        ):
            neckline = max(c.high for c in candles[first.index : second.index + 1])
            if (neckline - trough) / neckline >= t.double_top_tolerance:
                if close > neckline:
                    labels.append(f"Double Bottom, neckline {neckline:,.2f} broken")
                    bias = Bias.BULLISH
                else:
                    labels.append(f"Double Bottom candidate, neckline {neckline:,.2f} holding")
    if not labels:
        labels.append("No double top / bottom")
    return ChecklistCell(labels=labels, bias=bias, values={"close": _round(close)}, rule_ids=[rule])


def heikin_ashi_labels(candles: Sequence[Candle]) -> List[str]:
    """Latest Heikin-Ashi candle, its colour and its wicks (PAPA Concept 3).

    Wicks are read from the HA body: an upper wick if the HA high is above the body top, a lower wick if the HA low
    is below the body bottom. A candle with wicks on both sides is indecisive (yellow in the matrix). A candle with
    at most one wick is decisive and takes its colour, green or red.
    """
    if not candles:
        return []
    ha_open = ha_close = ha_high = ha_low = 0.0
    for index, candle in enumerate(candles):
        close_ = (candle.open + candle.high + candle.low + candle.close) / 4
        open_ = (candle.open + candle.close) / 2 if index == 0 else (ha_open + ha_close) / 2
        ha_open, ha_close = open_, close_
        ha_high = max(candle.high, open_, close_)
        ha_low = min(candle.low, open_, close_)
    body_top, body_bottom = max(ha_open, ha_close), min(ha_open, ha_close)
    upper_wick = not math.isclose(ha_high, body_top, rel_tol=1e-9, abs_tol=1e-9)
    lower_wick = not math.isclose(ha_low, body_bottom, rel_tol=1e-9, abs_tol=1e-9)
    wicks = {
        (True, True): "both wicks",
        (True, False): "upper wick",
        (False, True): "lower wick",
        (False, False): "no wicks",
    }[(upper_wick, lower_wick)]
    if ha_close > ha_open:
        return [f"Heikin-Ashi green, {wicks}"]
    if ha_close < ha_open:
        return [f"Heikin-Ashi red, {wicks}"]
    return [f"Heikin-Ashi doji, {wicks}"]


# Whole timeframe


def evaluate_timeframe(
    candles: Sequence[Candle],
    t: ChecklistThresholds,
    *,
    latest_candle_live: bool = False,
) -> TimeframeEvaluation:
    automated = [row.id for row in CHECKLIST_ROWS if row.automated]
    try:
        s = calculate_indicators(candles, t.indicators)
    except InvalidCandlesError as error:
        reason = str(error)
        return TimeframeEvaluation(
            cells={row_id: _unavailable(reason, row_id) for row_id in automated}, unavailable_reason=reason
        )

    cells: Dict[str, ChecklistCell] = {}
    pivot_highs, pivot_lows = find_pivots(s.highs, s.lows, t.pivot_window, t.pivot_window)
    trend = dow_trend(pivot_highs, pivot_lows)
    if trend.bias is Bias.UNAVAILABLE:
        cells["dow_trend"] = _unavailable("Fewer than two confirmed swing highs and lows.", "dow")
    else:
        cells["dow_trend"] = ChecklistCell(
            labels=[trend.label],
            bias=trend.bias,
            values={
                "previous_swing_high": trend.swing_highs[0].price,
                "last_swing_high": trend.swing_highs[1].price,
                "previous_swing_low": trend.swing_lows[0].price,
                "last_swing_low": trend.swing_lows[1].price,
            },
            rule_ids=["dow"],
        )

    structure_candles = candles[:-1] if latest_candle_live else candles
    structure_highs = [candle.high for candle in structure_candles]
    structure_lows = [candle.low for candle in structure_candles]
    v2_highs, v2_lows = find_pivots(
        structure_highs, structure_lows, t.pivot_window, t.pivot_window
    )
    v2_atr = _at(s.atr, 1 if latest_candle_live else 0)
    v2_swing_highs: List[SwingPoint] = []
    v2_swing_lows: List[SwingPoint] = []
    if structure_candles:
        v2 = analyze_dow_structure_v2(
            v2_highs,
            v2_lows,
            latest_close=structure_candles[-1].close,
            atr_value=v2_atr,
            significance_atr=t.dow_significance_atr,
        )
        values = {
            "latest_closed_candle_at": structure_candles[-1].timestamp.isoformat(),
            "latest_closed_close": structure_candles[-1].close,
            "used_closed_candles": len(structure_candles),
            "excluded_live_candle": latest_candle_live,
            "confirmation_lag_bars": t.pivot_window,
            "ambiguous_pivot_count": v2.ambiguous_pivot_count,
            "high_delta_atr": _round(v2.high_delta_atr, 2),
            "low_delta_atr": _round(v2.low_delta_atr, 2),
            "structural_moves_significant": v2.structural_moves_significant,
        }
        if len(v2.swing_highs) >= 2 and len(v2.swing_lows) >= 2:
            previous_high, last_high = v2.swing_highs
            previous_low, last_low = v2.swing_lows
            values.update(
                {
                    "previous_swing_high": previous_high.price,
                    "previous_swing_high_at": structure_candles[previous_high.index].timestamp.isoformat(),
                    "last_swing_high": last_high.price,
                    "last_swing_high_at": structure_candles[last_high.index].timestamp.isoformat(),
                    "previous_swing_low": previous_low.price,
                    "previous_swing_low_at": structure_candles[previous_low.index].timestamp.isoformat(),
                    "last_swing_low": last_low.price,
                    "last_swing_low_at": structure_candles[last_low.index].timestamp.isoformat(),
                }
            )
        v2_swing_highs, v2_swing_lows = v2.swing_highs, v2.swing_lows
        labels = [v2.label, v2.break_label]
        if v2.ambiguous_pivot_count:
            labels.append(f"{v2.ambiguous_pivot_count} ambiguous outside-bar pivot(s) omitted")
        cells["dow_structure_v2"] = ChecklistCell(
            labels=labels,
            bias=v2.bias,
            values=values,
            rule_ids=["dow-v2", "dow-v2-break", "dow-v2-significance"],
            unavailable_reason=(
                "Fewer than two confirmed alternating swing highs and lows."
                if v2.bias is Bias.UNAVAILABLE
                else None
            ),
        )
    else:
        cells["dow_structure_v2"] = _unavailable("No closed candles are available.", "dow-v2")

    cells["weapon_volume"] = volume_cell(structure_candles, t)
    close = s.closes[-1]
    atr_value = _at(s.atr)
    location = locate_price(close, pivot_highs, pivot_lows, atr_value, t.sr_proximity_atr)
    level_values = {
        "close": _round(close),
        "support": _round(location.support),
        "resistance": _round(location.resistance),
        "support_distance_atr": _round(location.support_distance_atr, 2),
        "resistance_distance_atr": _round(location.resistance_distance_atr, 2),
        "atr": _round(atr_value),
    }
    if location.kind is LocationKind.UNAVAILABLE:
        reason = "Needs swing levels and ATR."
        cells["location"] = _unavailable(reason, "location")
        cells["support_resistance"] = _unavailable(reason, "sr")
    else:
        location_bias = {
            LocationKind.NEAR_SUPPORT: Bias.BULLISH,
            LocationKind.NEAR_RESISTANCE: Bias.BEARISH,
            LocationKind.ABOVE_PRIOR_RESISTANCE: Bias.BULLISH,
            LocationKind.BELOW_PRIOR_SUPPORT: Bias.BEARISH,
        }.get(location.kind, Bias.NEUTRAL)
        cells["location"] = _with_labels(
            ChecklistCell(labels=[location.label], bias=location_bias, values=level_values, rule_ids=["location"]),
            _fibonacci_labels(structure_candles, v2_swing_highs, v2_swing_lows, t),
            "fib",
        )
        sr_labels = []
        if location.support is not None:
            sr_labels.append(f"Support {location.support:,.2f}")
        if location.resistance is not None:
            sr_labels.append(f"Resistance {location.resistance:,.2f}")
        cells["support_resistance"] = _with_labels(
            ChecklistCell(labels=sr_labels, bias=Bias.NEUTRAL, values=level_values, rule_ids=["sr"]),
            _breakout_labels(
                structure_candles,
                v2_highs,
                v2_lows,
                cells["weapon_volume"].values.get("volume_ratio"),
                t,
            ),
            "sr-breakout",
        )

    if len(candles) >= 2:
        action = price_action(candles[-2], candles[-1], trend.structure)
        cells["price_action"] = ChecklistCell(
            labels=action.labels,
            bias=action.bias,
            label_bias=action.label_biases,
            values={
                "open": candles[-1].open,
                "high": candles[-1].high,
                "low": candles[-1].low,
                "close": candles[-1].close,
                "prev_open": candles[-2].open,
                "prev_high": candles[-2].high,
                "prev_low": candles[-2].low,
                "prev_close": candles[-2].close,
            },
            rule_ids=["price_action"],
        )
    else:
        cells["price_action"] = _unavailable("Needs at least two candles.", "price_action")
    ha_labels = heikin_ashi_labels(structure_candles)
    cells["heikin_ashi"] = (
        ChecklistCell(labels=ha_labels, bias=Bias.NEUTRAL, rule_ids=["heikin-ashi"])
        if ha_labels
        else _unavailable("Needs candles for Heikin-Ashi.", "heikin-ashi")
    )

    patterns = detect_candle_patterns(
        candles,
        at_support=location.kind is LocationKind.NEAR_SUPPORT,
        at_resistance=location.kind is LocationKind.NEAR_RESISTANCE,
        wick_tolerance=t.wick_tolerance,
    )
    cells["candlestick_pattern"] = ChecklistCell(
        labels=patterns.labels, bias=patterns.bias, values={"location": location.label}, rule_ids=["candles"]
    )

    # Location only: the S&R bias sits on the location row and the pattern bias on candlestick_pattern.
    near_level = {
        LocationKind.NEAR_SUPPORT: "At / near support",
        LocationKind.NEAR_RESISTANCE: "At / near resistance",
    }.get(location.kind, "Not at support or resistance")
    cells["special_candles"] = ChecklistCell(
        labels=[near_level], bias=Bias.NEUTRAL, values={"location": location.label}, rule_ids=["candle-location"]
    )

    cells["bollinger"] = bollinger_cell(
        s.highs, s.lows, s.closes, s.bb_upper, s.bb_basis, s.bb_lower, t, forming=latest_candle_live
    )
    cells["rsi"] = rsi_cell(s.rsi, t)
    cells["dmi"] = dmi_cell(s.plus_di, s.minus_di, t)
    cells["adx"] = adx_cell(s.adx, s.plus_di, s.minus_di, t)
    cells["macd"] = macd_cell(s.macd_line, s.macd_signal, t)
    cells["stochastic"] = stochastic_cell(s.stoch_k, s.stoch_d, t)
    cells["emas"] = ema_cell(s.closes, s.ema, t)
    div_highs, div_lows = divergence_pivots(structure_highs, structure_lows, t)
    cells["divergence"] = divergence_cell(
        (("RSI", s.rsi), ("MACD", s.macd_line), ("Stochastic %K", s.stoch_k)),
        div_highs,
        div_lows,
        len(structure_candles),
        t,
    )
    cells["chart_pattern"] = chart_pattern_cell(structure_candles, v2_highs, v2_lows, t)

    if len(candles) >= 3:
        action_cell = cells["price_action"]
        action_labels = {
            label: action_cell.label_bias.get(label, action_cell.bias)
            for label in action_cell.labels
        }
        significant, significant_values = significant_candle_evidence(
            candles,
            pivot_highs,
            pivot_lows,
            t.pivot_window,
            at_support=location.kind is LocationKind.NEAR_SUPPORT,
            at_resistance=location.kind is LocationKind.NEAR_RESISTANCE,
            pattern_labels=patterns.labels,
            action_labels=action_labels,
            bollinger_labels=cells["bollinger"].labels,
            rsi_now=_at(s.rsi),
            rsi_prev=_at(s.rsi, 1),
            volume_ratio=cells["weapon_volume"].values.get("volume_ratio"),
            volume_threshold=t.volume_double_ratio,
        )
        cells["significant_candle"] = ChecklistCell(
            labels=significant.labels,
            bias=significant.bias,
            label_bias=significant.label_biases,
            values=significant_values,
            rule_ids=["significant-candle"],
        )
    else:
        cells["significant_candle"] = _unavailable("Needs at least three candles.", "significant-candle")

    return TimeframeEvaluation(
        cells=cells, series=s, last_close=close, last_candle_at=candles[-1].timestamp
    )
