"""Pure price-structure evidence: swing pivots, Dow trend, location, price action, candles.

Wording follows the PAPA/SMM course notes and the user's multi-timeframe worksheet.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Sequence

from .models import Bias, Candle


@dataclass(frozen=True)
class Pivot:
    index: int
    price: float


class TrendStructure(str, Enum):
    UP = "up"
    DOWN = "down"
    SIDEWAYS = "sideways"
    UNAVAILABLE = "unavailable"


_TREND_LABELS = {
    TrendStructure.UP: ("HH - HL (Up Trend)", Bias.BULLISH),
    TrendStructure.DOWN: ("LL - LH (Down Trend)", Bias.BEARISH),
    TrendStructure.SIDEWAYS: ("HLs - LHs (Sideways Trend)", Bias.NEUTRAL),
    TrendStructure.UNAVAILABLE: ("Not enough swings", Bias.UNAVAILABLE),
}


@dataclass(frozen=True)
class DowTrend:
    structure: TrendStructure
    label: str
    bias: Bias
    swing_highs: tuple[Pivot, ...] = ()
    swing_lows: tuple[Pivot, ...] = ()


class LocationKind(str, Enum):
    NEAR_SUPPORT = "near_support"
    NEAR_RESISTANCE = "near_resistance"
    MID_RANGE = "mid_range"
    ABOVE_PRIOR_RESISTANCE = "above_prior_resistance"
    BELOW_PRIOR_SUPPORT = "below_prior_support"
    UNAVAILABLE = "unavailable"


LOCATION_LABELS = {
    LocationKind.NEAR_SUPPORT: "Near Support",
    LocationKind.NEAR_RESISTANCE: "Near Resistance",
    LocationKind.MID_RANGE: "Mid-range",
    LocationKind.ABOVE_PRIOR_RESISTANCE: "Above prior resistance",
    LocationKind.BELOW_PRIOR_SUPPORT: "Below prior support",
    LocationKind.UNAVAILABLE: "Not enough swings",
}


@dataclass(frozen=True)
class PriceLocation:
    kind: LocationKind
    support: Optional[float] = None
    resistance: Optional[float] = None
    support_distance_atr: Optional[float] = None
    resistance_distance_atr: Optional[float] = None

    @property
    def label(self) -> str:
        return LOCATION_LABELS[self.kind]


@dataclass(frozen=True)
class Evidence:
    labels: List[str] = field(default_factory=list)
    bias: Bias = Bias.NEUTRAL


def find_pivots(
    highs: Sequence[float], lows: Sequence[float], left: int, right: int
) -> tuple[List[Pivot], List[Pivot]]:
    """Confirmed swing highs/lows: strictly beyond the left side, not exceeded on the right."""
    pivot_highs: List[Pivot] = []
    pivot_lows: List[Pivot] = []
    for i in range(left, len(highs) - right):
        if all(highs[i] > highs[j] for j in range(i - left, i)) and all(
            highs[i] >= highs[j] for j in range(i + 1, i + right + 1)
        ):
            pivot_highs.append(Pivot(i, highs[i]))
        if all(lows[i] < lows[j] for j in range(i - left, i)) and all(
            lows[i] <= lows[j] for j in range(i + 1, i + right + 1)
        ):
            pivot_lows.append(Pivot(i, lows[i]))
    return pivot_highs, pivot_lows


def dow_trend(pivot_highs: Sequence[Pivot], pivot_lows: Sequence[Pivot]) -> DowTrend:
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        label, bias = _TREND_LABELS[TrendStructure.UNAVAILABLE]
        return DowTrend(TrendStructure.UNAVAILABLE, label, bias)
    previous_high, last_high = pivot_highs[-2], pivot_highs[-1]
    previous_low, last_low = pivot_lows[-2], pivot_lows[-1]
    if last_high.price > previous_high.price and last_low.price > previous_low.price:
        structure = TrendStructure.UP
    elif last_high.price < previous_high.price and last_low.price < previous_low.price:
        structure = TrendStructure.DOWN
    else:
        structure = TrendStructure.SIDEWAYS
    label, bias = _TREND_LABELS[structure]
    return DowTrend(structure, label, bias, (previous_high, last_high), (previous_low, last_low))


def locate_price(
    close: float,
    pivot_highs: Sequence[Pivot],
    pivot_lows: Sequence[Pivot],
    atr_value: Optional[float],
    proximity_atr: float,
) -> PriceLocation:
    """Nearest swing level on each side; a broken level changes role (impact line)."""
    if atr_value is None or atr_value <= 0 or not (pivot_highs or pivot_lows):
        return PriceLocation(LocationKind.UNAVAILABLE)
    levels = [p.price for p in (*pivot_highs, *pivot_lows)]
    below = [level for level in levels if level <= close]
    above = [level for level in levels if level > close]
    support = max(below) if below else None
    resistance = min(above) if above else None
    support_distance = (close - support) / atr_value if support is not None else None
    resistance_distance = (resistance - close) / atr_value if resistance is not None else None

    near_support = support_distance is not None and support_distance <= proximity_atr
    near_resistance = resistance_distance is not None and resistance_distance <= proximity_atr
    if near_support and near_resistance:
        kind = LocationKind.NEAR_SUPPORT if support_distance <= resistance_distance else LocationKind.NEAR_RESISTANCE
    elif near_support:
        kind = LocationKind.NEAR_SUPPORT
    elif near_resistance:
        kind = LocationKind.NEAR_RESISTANCE
    elif resistance is None:
        kind = LocationKind.ABOVE_PRIOR_RESISTANCE
    elif support is None:
        kind = LocationKind.BELOW_PRIOR_SUPPORT
    else:
        kind = LocationKind.MID_RANGE
    return PriceLocation(kind, support, resistance, support_distance, resistance_distance)


def _is_bullish(c: Candle) -> bool:
    return c.close > c.open


def _is_bearish(c: Candle) -> bool:
    return c.close < c.open


def price_action(previous: Candle, current: Candle, wick_tolerance: float = 0.02) -> Evidence:
    """Compare the current candle's open/close with the previous candle (PAPA Advanced Dow)."""
    labels: List[str] = []
    if _is_bearish(previous) and current.close > previous.close:
        labels.append("Close > Prev. Bearish Close")
        if current.close > previous.open:
            labels.append("Close > Prev. Bearish Open")
    if _is_bullish(previous) and current.close < previous.close:
        labels.append("Close < Prev. Bullish Close")
        if current.close < previous.open:
            labels.append("Close < Prev. Bullish Open")
    if current.close > previous.high:
        labels.append("Close > Prev. Candle High")
    if current.close < previous.low:
        labels.append("Close < Prev. Candle Low")

    if current.open > previous.high:
        labels.append("Gap up")
    elif current.open > previous.close:
        labels.append("Bullish Open (above Prev. Close)")
    elif current.open < previous.low:
        labels.append("Gap down")
    elif current.open < previous.close:
        labels.append("Bearish Open (below Prev. Close)")

    tolerance = (current.high - current.low) * wick_tolerance
    if current.high > current.low:
        if _is_bullish(current) and current.open - current.low <= tolerance:
            labels.append("Strong Bullish Open (Open = Low)")
        if _is_bullish(current) and current.high - current.close <= tolerance:
            labels.append("Strong Bullish Close (Close = High)")
        if _is_bearish(current) and current.high - current.open <= tolerance:
            labels.append("Strong Bearish Open (Open = High)")
        if _is_bearish(current) and current.close - current.low <= tolerance:
            labels.append("Strong Bearish Close (Close = Low)")

    if current.close > previous.high:
        bias = Bias.BULLISH
    elif current.close < previous.low:
        bias = Bias.BEARISH
    elif current.close > previous.close:
        bias = Bias.BULLISH
    elif current.close < previous.close:
        bias = Bias.BEARISH
    else:
        bias = Bias.NEUTRAL
    return Evidence(labels or ["Close = Prev. Close"], bias)


def _prior_direction(candles: Sequence[Candle], lookback: int = 5) -> Optional[str]:
    if len(candles) < lookback + 2:
        return None
    reference, latest = candles[-lookback - 2].close, candles[-2].close
    if latest > reference:
        return "top"
    if latest < reference:
        return "bottom"
    return None


def _single_candle_pattern(c: Candle) -> Optional[str]:
    candle_range = c.high - c.low
    if candle_range <= 0:
        return None
    body = abs(c.close - c.open)
    upper = c.high - max(c.open, c.close)
    lower = min(c.open, c.close) - c.low
    if lower >= 2 * body and upper <= 0.25 * candle_range:
        return "hammer"
    if upper >= 2 * body and lower <= 0.25 * candle_range:
        return "inverted_hammer"
    if body <= 0.1 * candle_range:
        return "doji"
    if body <= 0.3 * candle_range and upper >= 0.2 * candle_range and lower >= 0.2 * candle_range:
        return "spinning_top"
    return None


def detect_candle_patterns(candles: Sequence[Candle], at_support: bool, at_resistance: bool) -> Evidence:
    """Candlestick patterns ending at the latest candle, annotated with location."""
    if not candles:
        return Evidence(["No candles"], Bias.UNAVAILABLE)
    context = "bottom" if at_support else "top" if at_resistance else _prior_direction(candles)
    found: List[tuple[str, Bias]] = []
    current = candles[-1]

    shape = _single_candle_pattern(current)
    if shape == "hammer":
        found.append(("Hanging Man", Bias.BEARISH) if context == "top" else ("Hammer", Bias.BULLISH))
    elif shape == "inverted_hammer":
        found.append(("Inverted Hammer", Bias.BEARISH))
    elif shape == "doji":
        found.append(("Doji", Bias.NEUTRAL))
    elif shape == "spinning_top":
        found.append(("Spinning Top", Bias.NEUTRAL))

    if len(candles) >= 2:
        previous = candles[-2]
        previous_body = abs(previous.close - previous.open)
        current_body = abs(current.close - current.open)
        previous_mid = (previous.open + previous.close) / 2
        if (
            _is_bearish(previous)
            and _is_bullish(current)
            and current.open <= previous.close
            and current.close >= previous.open
            and current_body > previous_body
        ):
            found.append(("Bullish Engulf", Bias.BULLISH))
        elif (
            _is_bullish(previous)
            and _is_bearish(current)
            and current.open >= previous.close
            and current.close <= previous.open
            and current_body > previous_body
        ):
            found.append(("Bearish Engulf", Bias.BEARISH))
        elif (
            _is_bearish(previous)
            and _is_bullish(current)
            and current.open < previous.close
            and previous_mid < current.close < previous.open
        ):
            found.append(("Bullish Piercing", Bias.BULLISH))
        elif (
            _is_bullish(previous)
            and _is_bearish(current)
            and current.open > previous.close
            and previous.open < current.close < previous_mid
        ):
            found.append(("Bearish Piercing", Bias.BEARISH))
        if current.high <= previous.high and current.low >= previous.low:
            found.append(("Mother candle", Bias.NEUTRAL))

    if len(candles) >= 3:
        first, middle = candles[-3], candles[-2]
        first_body = abs(first.close - first.open)
        first_range = first.high - first.low
        middle_body = abs(middle.close - middle.open)
        first_mid = (first.open + first.close) / 2
        if first_range > 0 and first_body >= 0.5 * first_range and middle_body <= 0.3 * first_body:
            if _is_bearish(first) and _is_bullish(current) and current.close > first_mid:
                found.append(("Morning Star", Bias.BULLISH))
            elif _is_bullish(first) and _is_bearish(current) and current.close < first_mid:
                found.append(("Evening Star", Bias.BEARISH))

    if not found:
        return Evidence(["No special candle"], Bias.NEUTRAL)

    suffix = " in Support" if at_support else " at Resistance" if at_resistance else ""
    labels = [f"{name}{suffix}" for name, _ in found]
    directional = {bias for _, bias in found if bias is not Bias.NEUTRAL}
    bias = directional.pop() if len(directional) == 1 else Bias.NEUTRAL
    return Evidence(labels, bias)
