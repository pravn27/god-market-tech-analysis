"""PAPA + SMM multi-timeframe checklist rules (profile ``mtf-checklist-v1``).

Each rule turns local indicator/price-structure evidence into the wording of the
user's worksheet. Rules are pure functions over plain series so every row of the
specification's rule tables can be tested directly.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Mapping, Optional, Sequence

from .models import Bias, Candle, ChecklistCell
from .price_structure import (
    LocationKind,
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
    sr_proximity_atr: float = 1.0
    macd_near_zero_fraction: float = 0.10
    macd_zero_range_window: int = 50
    wick_tolerance: float = 0.02

    @property
    def version(self) -> str:
        return self.indicators.version


@dataclass(frozen=True)
class ChecklistRow:
    id: str
    section: str
    label: str
    automated: bool


SECTION_CONTEXT = "1. Overall Context / View / Dow Theory"
SECTION_PRICE_ACTION = "2. Dow Theory Advanced + Price Action"
SECTION_INDICATORS = "3. Check Indicators"
SECTION_SETUPS = "5. Concepts / Setups / Confirmation"

CHECKLIST_ROWS: tuple[ChecklistRow, ...] = (
    ChecklistRow("dow_trend", SECTION_CONTEXT, "Overall Context / View / Dow Theory", True),
    ChecklistRow("location", SECTION_CONTEXT, "Where do you stand in overall trend / context?", True),
    ChecklistRow("support_resistance", SECTION_CONTEXT, "Support / Resistance (horizontal swing levels)", True),
    ChecklistRow("trendlines", SECTION_CONTEXT, "Angular trendlines", False),
    ChecklistRow("significant_candles", SECTION_CONTEXT, "Mark significant & event candles", False),
    ChecklistRow("price_action", SECTION_PRICE_ACTION, "Current candle OPEN / CLOSE vs previous candle OHLC", True),
    ChecklistRow("special_candles", SECTION_PRICE_ACTION, "Special candles near / at support & resistance", True),
    ChecklistRow("bollinger", SECTION_INDICATORS, "Bollinger Band", True),
    ChecklistRow("rsi", SECTION_INDICATORS, "RSI", True),
    ChecklistRow("dmi", SECTION_INDICATORS, "DMI", True),
    ChecklistRow("adx", SECTION_INDICATORS, "ADX", True),
    ChecklistRow("macd", SECTION_INDICATORS, "MACD", True),
    ChecklistRow("stochastic", SECTION_INDICATORS, "Stochastic", True),
    ChecklistRow("emas", SECTION_INDICATORS, "EMAs", True),
    ChecklistRow("chart_pattern", SECTION_SETUPS, "Concepts / Setups / Chart Patterns", False),
    ChecklistRow("weapon_candle", SECTION_SETUPS, "Significant / Weapon / Confirmation candle", False),
    ChecklistRow("weapon_volume", SECTION_SETUPS, "Volume of weapon candle", False),
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
) -> ChecklistCell:
    rule = "bb"
    u, m, l = _at(upper), _at(basis), _at(lower)
    lookback = t.slope_lookback
    u_prev, l_prev = _at(upper, lookback), _at(lower, lookback)
    if None in (u, m, l, u_prev, l_prev):
        return _unavailable(_needs(t.indicators.bb_period + lookback), rule)

    def change(now: float, before: float) -> float:
        return (now - before) / abs(before) if before else 0.0

    upper_expanding = change(u, u_prev) > t.bb_flat_tolerance
    lower_expanding = -change(l, l_prev) > t.bb_flat_tolerance
    upper_flat = abs(change(u, u_prev)) <= t.bb_flat_tolerance
    lower_flat = abs(change(l, l_prev)) <= t.bb_flat_tolerance
    recent = range(t.recent_crossover_periods)
    upper_touched = any(
        _at(upper, k) is not None and highs[len(highs) - 1 - k] >= _at(upper, k) for k in recent
    )
    lower_touched = any(
        _at(lower, k) is not None and lows[len(lows) - 1 - k] <= _at(lower, k) for k in recent
    )
    close, width = closes[-1], u - l

    if highs[-1] >= u and upper_expanding:
        labels, bias, rule = ["UBBC, BB Expands"], Bias.BULLISH, "bb.ubbc"
    elif lows[-1] <= l and lower_expanding:
        labels, bias, rule = ["LBBC, BB Expands"], Bias.BEARISH, "bb.lbbc"
    elif upper_touched and not upper_expanding:
        labels, bias, rule = ["UBBC Failure, BKT"], Bias.BEARISH, "bb.bkt"
    elif lower_touched and not lower_expanding:
        labels, bias, rule = ["LBBC Failure, BKP"], Bias.BULLISH, "bb.bkp"
    elif abs(close - m) <= t.bb_near_median_fraction * width:
        labels, bias, rule = ["Price is Near Median"], Bias.NEUTRAL, "bb.median"
    elif close > m:
        labels, bias, rule = ["Price is Above Median"], Bias.BULLISH, "bb.median"
    else:
        labels, bias, rule = ["Price is Below Median"], Bias.BEARISH, "bb.median"

    width_prev = u_prev - l_prev
    if upper_flat and lower_flat:
        labels.append("Bands are Flat")
    elif width_prev and width > width_prev * (1 + t.bb_flat_tolerance):
        labels.append("Bands Expanding")
    elif width_prev and width < width_prev * (1 - t.bb_flat_tolerance):
        labels.append("Bands Contracting")
    else:
        labels.append("Bands are Flat")

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
    labels = [label]
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

    labels = [headline]
    if not cross and tick in ("up", "down"):
        labels.append("Up tick" if tick == "up" else "Down tick")
    labels.append("PCO state" if k_value > d_value else "NCO state" if k_value < d_value else "K = D")
    return ChecklistCell(
        labels=labels, bias=bias, values={"k": _round(k_value, 2), "d": _round(d_value, 2)}, rule_ids=["stoch"]
    )


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
    e5, e13, e26, e50 = (latest[p] for p in required)
    poc = e5 > e13 > e26
    noc = e5 < e13 < e26
    if poc:
        labels.append("POC, 5 > 13 > 26")
    elif noc:
        labels.append("NOC, 5 < 13 < 26")
    else:
        labels.append("EMAs intermingled")
    e100, e150, e200 = latest.get(100), latest.get(150), latest.get(200)
    if None not in (e100, e150, e200):
        if e100 > e150 > e200:
            labels.append("POC, 100 > 150 > 200")
        elif e100 < e150 < e200:
            labels.append("NOC, 100 < 150 < 200")
    for slow in (13, 26):
        cross = _recent_cross(emas[5], emas[slow], t.recent_crossover_periods)
        if cross:
            labels.append(f"5 EMA {'PCO' if cross[0] == 'up' else 'NCO'} with {slow} EMA")

    if close > e50 and poc:
        bias = Bias.BULLISH
    elif close < e50 and noc:
        bias = Bias.BEARISH
    else:
        bias = Bias.NEUTRAL
    values = {f"ema_{p}": _round(latest.get(p)) for p in t.indicators.ema_periods}
    values["close"] = _round(close)
    return ChecklistCell(labels=labels, bias=bias, values=values, rule_ids=["ema"])


# Whole timeframe


def evaluate_timeframe(candles: Sequence[Candle], t: ChecklistThresholds) -> TimeframeEvaluation:
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
        cells["location"] = ChecklistCell(
            labels=[location.label], bias=location_bias, values=level_values, rule_ids=["location"]
        )
        sr_labels = []
        if location.support is not None:
            sr_labels.append(f"Support {location.support:,.2f}")
        if location.resistance is not None:
            sr_labels.append(f"Resistance {location.resistance:,.2f}")
        cells["support_resistance"] = ChecklistCell(
            labels=sr_labels, bias=Bias.NEUTRAL, values=level_values, rule_ids=["sr"]
        )

    if len(candles) >= 2:
        action = price_action(candles[-2], candles[-1], t.wick_tolerance)
        cells["price_action"] = ChecklistCell(
            labels=action.labels,
            bias=action.bias,
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

    patterns = detect_candle_patterns(
        candles,
        at_support=location.kind is LocationKind.NEAR_SUPPORT,
        at_resistance=location.kind is LocationKind.NEAR_RESISTANCE,
    )
    cells["special_candles"] = ChecklistCell(
        labels=patterns.labels, bias=patterns.bias, values={"location": location.label}, rule_ids=["candles"]
    )

    cells["bollinger"] = bollinger_cell(s.highs, s.lows, s.closes, s.bb_upper, s.bb_basis, s.bb_lower, t)
    cells["rsi"] = rsi_cell(s.rsi, t)
    cells["dmi"] = dmi_cell(s.plus_di, s.minus_di, t)
    cells["adx"] = adx_cell(s.adx, s.plus_di, s.minus_di, t)
    cells["macd"] = macd_cell(s.macd_line, s.macd_signal, t)
    cells["stochastic"] = stochastic_cell(s.stoch_k, s.stoch_d, t)
    cells["emas"] = ema_cell(s.closes, s.ema, t)

    return TimeframeEvaluation(
        cells=cells, series=s, last_close=close, last_candle_at=candles[-1].timestamp
    )
