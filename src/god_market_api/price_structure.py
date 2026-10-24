"""Pure price-structure evidence: swing pivots, Dow trend, location, price action, candles.

Wording follows the PAPA/SMM course notes and the user's multi-timeframe worksheet.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Sequence

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


class SwingKind(str, Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class SwingPoint:
    kind: SwingKind
    index: int
    price: float


@dataclass(frozen=True)
class NormalizedSwings:
    swings: tuple[SwingPoint, ...]
    ambiguous_pivot_count: int = 0


class DowStructureV2Kind(str, Enum):
    UP = "up"
    DOWN = "down"
    CONTRACTING_RANGE = "contracting_range"
    EXPANDING_RANGE = "expanding_range"
    TRANSITION = "transition"
    UNAVAILABLE = "unavailable"


_DOW_V2_LABELS = {
    DowStructureV2Kind.UP: ("HH - HL (Up Trend)", Bias.BULLISH),
    DowStructureV2Kind.DOWN: ("LL - LH (Down Trend)", Bias.BEARISH),
    DowStructureV2Kind.CONTRACTING_RANGE: ("LH - HL (Contracting Range)", Bias.NEUTRAL),
    DowStructureV2Kind.EXPANDING_RANGE: ("HH - LL (Expanding Range)", Bias.NEUTRAL),
    DowStructureV2Kind.TRANSITION: ("Equal / Transitional Structure", Bias.NEUTRAL),
    DowStructureV2Kind.UNAVAILABLE: ("Not enough alternating swings", Bias.UNAVAILABLE),
}


@dataclass(frozen=True)
class DowStructureV2:
    structure: DowStructureV2Kind
    label: str
    bias: Bias
    break_label: str
    swings: tuple[SwingPoint, ...] = ()
    swing_highs: tuple[SwingPoint, ...] = ()
    swing_lows: tuple[SwingPoint, ...] = ()
    high_delta_atr: Optional[float] = None
    low_delta_atr: Optional[float] = None
    structural_moves_significant: Optional[bool] = None
    ambiguous_pivot_count: int = 0


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
    # Optional per-label direction; labels without an entry take the overall bias.
    label_biases: Dict[str, Bias] = field(default_factory=dict)


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


def normalize_alternating_swings(
    pivot_highs: Sequence[Pivot], pivot_lows: Sequence[Pivot]
) -> NormalizedSwings:
    """Order pivots into alternating legs without guessing same-candle intrabar order."""
    high_indices = {pivot.index for pivot in pivot_highs}
    low_indices = {pivot.index for pivot in pivot_lows}
    ambiguous_indices = high_indices & low_indices
    events = [
        SwingPoint(SwingKind.HIGH, pivot.index, pivot.price)
        for pivot in pivot_highs
        if pivot.index not in ambiguous_indices
    ]
    events.extend(
        SwingPoint(SwingKind.LOW, pivot.index, pivot.price)
        for pivot in pivot_lows
        if pivot.index not in ambiguous_indices
    )
    events.sort(key=lambda swing: swing.index)

    normalized: List[SwingPoint] = []
    for event in events:
        if not normalized or normalized[-1].kind is not event.kind:
            normalized.append(event)
            continue
        previous = normalized[-1]
        is_more_extreme = (
            event.price > previous.price
            if event.kind is SwingKind.HIGH
            else event.price < previous.price
        )
        if is_more_extreme:
            normalized[-1] = event
    return NormalizedSwings(tuple(normalized), len(ambiguous_indices))


def _structure_break_label(
    structure: DowStructureV2Kind,
    latest_close: float,
    last_high: SwingPoint,
    last_low: SwingPoint,
) -> str:
    if latest_close > last_high.price:
        if structure is DowStructureV2Kind.UP:
            return "Bullish continuation (BOS)"
        if structure is DowStructureV2Kind.DOWN:
            return "Possible bullish change of character"
        return "Bullish structure break"
    if latest_close < last_low.price:
        if structure is DowStructureV2Kind.DOWN:
            return "Bearish continuation (BOS)"
        if structure is DowStructureV2Kind.UP:
            return "Possible bearish change of character"
        return "Bearish structure break"
    return "No confirmed structure break"


def analyze_dow_structure_v2(
    pivot_highs: Sequence[Pivot],
    pivot_lows: Sequence[Pivot],
    *,
    latest_close: float,
    atr_value: Optional[float],
    significance_atr: float = 0.5,
) -> DowStructureV2:
    """Classify an alternating confirmed swing sequence and its latest closed-price break."""
    if significance_atr < 0:
        raise ValueError("significance_atr must be non-negative.")
    normalized = normalize_alternating_swings(pivot_highs, pivot_lows)
    highs = tuple(swing for swing in normalized.swings if swing.kind is SwingKind.HIGH)
    lows = tuple(swing for swing in normalized.swings if swing.kind is SwingKind.LOW)
    if len(highs) < 2 or len(lows) < 2:
        label, bias = _DOW_V2_LABELS[DowStructureV2Kind.UNAVAILABLE]
        return DowStructureV2(
            DowStructureV2Kind.UNAVAILABLE,
            label,
            bias,
            "No confirmed structure break",
            normalized.swings,
            highs,
            lows,
            ambiguous_pivot_count=normalized.ambiguous_pivot_count,
        )

    previous_high, last_high = highs[-2:]
    previous_low, last_low = lows[-2:]
    if last_high.price > previous_high.price and last_low.price > previous_low.price:
        structure = DowStructureV2Kind.UP
    elif last_high.price < previous_high.price and last_low.price < previous_low.price:
        structure = DowStructureV2Kind.DOWN
    elif last_high.price < previous_high.price and last_low.price > previous_low.price:
        structure = DowStructureV2Kind.CONTRACTING_RANGE
    elif last_high.price > previous_high.price and last_low.price < previous_low.price:
        structure = DowStructureV2Kind.EXPANDING_RANGE
    else:
        structure = DowStructureV2Kind.TRANSITION

    break_label = _structure_break_label(structure, latest_close, last_high, last_low)

    high_delta_atr = low_delta_atr = None
    significant = None
    if atr_value is not None and atr_value > 0:
        high_delta_atr = abs(last_high.price - previous_high.price) / atr_value
        low_delta_atr = abs(last_low.price - previous_low.price) / atr_value
        significant = high_delta_atr >= significance_atr and low_delta_atr >= significance_atr

    label, bias = _DOW_V2_LABELS[structure]
    return DowStructureV2(
        structure,
        label,
        bias,
        break_label,
        normalized.swings,
        (previous_high, last_high),
        (previous_low, last_low),
        high_delta_atr,
        low_delta_atr,
        significant,
        normalized.ambiguous_pivot_count,
    )


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


def _marching(candles: Sequence[Candle], rising: bool) -> bool:
    """Three candles closing progressively higher (or lower), each opening inside the prior real body."""
    for previous, current in zip(candles, candles[1:]):
        if rising and not current.close > previous.close:
            return False
        if not rising and not current.close < previous.close:
            return False
        low, high = sorted((previous.open, previous.close))
        if not low <= current.open <= high:
            return False
    return True


def price_action(
    previous: Candle, current: Candle, trend: TrendStructure = TrendStructure.UNAVAILABLE
) -> Evidence:
    """Current candle against the previous candle (PAPA "Dow Theory Advanced", the Bullish/Bearish Reversal terms).

    ``trend`` is section 1's Dow trend before this candle. Each label carries its own direction (``label_biases``);
    the cell bias is bullish if only bullish terms are present, bearish if only bearish, else neutral.
    Bullish side (previous bearish, current bullish): Confirmation above the previous Close and Low, Continuation
    above the previous High. Bearish side mirrors it (previous bullish, current bearish). A close beyond the previous
    High or Low is a Reversal Confirmation, whatever the colour; it also tags "Down trend stopped" (bullish) or
    "Up trend stopped" (bearish) when the trend before was the opposite one. In a trend, a close beyond the previous
    Low (up) or High (down) is a Continuation. Strong-candle (no wick) labels live in ``strong_candle_labels``.
    """
    # (label, direction): +1 bullish term, -1 bearish term.
    found: List[tuple[str, int]] = []
    if _is_bearish(previous) and _is_bullish(current):
        if current.close > previous.close:
            found.append(("Confirmation: Close > Prev. Bearish Close", 1))
        if current.close > previous.low:
            found.append(("Confirmation: Close > Prev. Bearish Low", 1))
        if current.close > previous.high:
            found.append(("Continuation: Close > Prev. Bearish High", 1))
    if _is_bullish(previous) and _is_bearish(current):
        if current.close < previous.close:
            found.append(("Confirmation: Close < Prev. Bullish Close", -1))
        if current.close < previous.high:
            found.append(("Confirmation: Close < Prev. Bullish High", -1))
        if current.close < previous.low:
            found.append(("Continuation: Close < Prev. Bullish Low", -1))

    if current.close > previous.high:
        found.append(("Reversal Confirmation: Close > Prev. Candle High", 1))
        if trend is TrendStructure.DOWN:
            found.append(("Down trend stopped", 1))
    elif current.close < previous.low:
        found.append(("Reversal Confirmation: Close < Prev. Candle Low", -1))
        if trend is TrendStructure.UP:
            found.append(("Up trend stopped", -1))

    if trend is TrendStructure.UP and current.close > previous.low:
        found.append(("Continuation: Close > Prev. Candle Low", 1))
    if trend is TrendStructure.DOWN and current.close < previous.high:
        found.append(("Continuation: Close < Prev. Candle High", -1))

    if current.open > previous.high:
        found.append(("Gap up", 1))
    elif current.open > previous.close:
        found.append(("Bullish Open (above Prev. Close)", 1))
    elif current.open < previous.low:
        found.append(("Gap down", -1))
    elif current.open < previous.close:
        found.append(("Bearish Open (below Prev. Close)", -1))

    labels = [label for label, _ in found]
    up = any(direction == 1 for _, direction in found)
    down = any(direction == -1 for _, direction in found)
    bias = Bias.BULLISH if up and not down else Bias.BEARISH if down and not up else Bias.NEUTRAL
    label_biases = {label: _direction_bias(direction) for label, direction in found}
    return Evidence(labels or ["Close = Prev. Close"], bias, label_biases)


def _direction_bias(direction: int) -> Bias:
    return Bias.BULLISH if direction > 0 else Bias.BEARISH if direction < 0 else Bias.NEUTRAL


def _prior_direction(candles: Sequence[Candle], lookback: int = 5) -> Optional[str]:
    if len(candles) < lookback + 2:
        return None
    reference, latest = candles[-lookback - 2].close, candles[-2].close
    if latest > reference:
        return "top"
    if latest < reference:
        return "bottom"
    return None


WICK_TOLERANCE = 0.02
STRONG_BULLISH = "Strong Bullish Candle (no upper & lower wicks)"
STRONG_BEARISH = "Strong Bearish Candle (no upper & lower wicks)"


def strong_candle_labels(candle: Candle, wick_tolerance: float = WICK_TOLERANCE) -> List[str]:
    """PAPA open/close rules on one candle: Open = Low / Close = High, and the bearish mirror.

    The combined label is added only when both ends hold, i.e. the candle has no upper and lower wick.
    """
    if candle.high <= candle.low:
        return []
    tolerance = (candle.high - candle.low) * wick_tolerance
    labels: List[str] = []
    if _is_bullish(candle):
        open_at_low = candle.open - candle.low <= tolerance
        close_at_high = candle.high - candle.close <= tolerance
        if open_at_low:
            labels.append("Strong Bullish Open (Open = Low)")
        if close_at_high:
            labels.append("Strong Bullish Close (Close = High)")
        if open_at_low and close_at_high:
            labels.append(STRONG_BULLISH)
    if _is_bearish(candle):
        open_at_high = candle.high - candle.open <= tolerance
        close_at_low = candle.close - candle.low <= tolerance
        if open_at_high:
            labels.append("Strong Bearish Open (Open = High)")
        if close_at_low:
            labels.append("Strong Bearish Close (Close = Low)")
        if open_at_high and close_at_low:
            labels.append(STRONG_BEARISH)
    return labels


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
    # PAPA: High Wave has a small body with big wicks on both sides; Spinning Top has smaller wicks.
    if body <= 0.3 * candle_range and upper >= 0.35 * candle_range and lower >= 0.35 * candle_range:
        return "high_wave"
    if body <= 0.3 * candle_range and upper >= 0.2 * candle_range and lower >= 0.2 * candle_range:
        return "spinning_top"
    return None


def detect_candle_patterns(
    candles: Sequence[Candle],
    at_support: bool,
    at_resistance: bool,
    wick_tolerance: float = WICK_TOLERANCE,
) -> Evidence:
    """Candlestick patterns ending at the latest candle (SMM Summary and PAPA Candles Imp), annotated with location.

    The same pattern can mean less at the other end of the trend: PAPA says an Engulf or Inverted Hammer
    at the top is not significantly bullish, a Morning Star at the top is a caution for bulls, and so on.
    In that case the bias is neutral and a separate label says why. Outside those cases the bias is unchanged.
    """
    if not candles:
        return Evidence(["No candles"], Bias.UNAVAILABLE)
    context = "bottom" if at_support else "top" if at_resistance else _prior_direction(candles)
    # (name, bias, note). The note becomes its own label when the location weakens the pattern.
    found: List[tuple[str, Bias, Optional[str]]] = []
    current = candles[-1]

    shape = _single_candle_pattern(current)
    # PAPA: Hammer and Inverted Hammer matter only at the end of a trend; ignored in the middle of a trend or range.
    if shape == "hammer":
        if context == "top":
            found.append(("Hanging Man", Bias.BEARISH, None))
        elif context is None:
            found.append(("Hammer", Bias.NEUTRAL, "Ignore mid-trend"))
        else:
            found.append(("Hammer", Bias.BULLISH, None))
    elif shape == "inverted_hammer":
        if context == "bottom":
            found.append(("Inverted Hammer", Bias.NEUTRAL, "Not significantly bearish at bottom"))
        elif context is None:
            found.append(("Inverted Hammer", Bias.NEUTRAL, "Ignore mid-trend"))
        else:
            found.append(("Inverted Hammer", Bias.BEARISH, None))
    elif shape == "doji":
        found.append(("Doji", Bias.NEUTRAL, None))
    elif shape == "high_wave":
        found.append(("High Wave", Bias.NEUTRAL, None))
    elif shape == "spinning_top":
        found.append(("Spinning Top", Bias.NEUTRAL, None))

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
            if context == "top":
                found.append(("Bullish Engulf", Bias.NEUTRAL, "Not significantly bullish at top"))
            else:
                found.append(("Bullish Engulf", Bias.BULLISH, None))
        elif (
            _is_bullish(previous)
            and _is_bearish(current)
            and current.open >= previous.close
            and current.close <= previous.open
            and current_body > previous_body
        ):
            if context == "bottom":
                found.append(("Bearish Engulf", Bias.NEUTRAL, "Not significantly bearish at bottom"))
            else:
                found.append(("Bearish Engulf", Bias.BEARISH, None))
        elif (
            _is_bearish(previous)
            and _is_bullish(current)
            and current.open < previous.close
            and previous_mid < current.close < previous.open
        ):
            found.append(("Bullish Piercing", Bias.BULLISH, None))
        elif (
            _is_bullish(previous)
            and _is_bearish(current)
            and current.open > previous.close
            and previous.open < current.close < previous_mid
        ):
            # PAPA names this same candle Dark Cloud Cover (gap-up opening bearish candle; significant at top of trend).
            found.append(("Bearish Piercing (Dark Cloud Cover)", Bias.BEARISH, None))
        # PAPA classes Harami as a neutral pattern. The note says where it is significant; the bias stays neutral.
        if (
            _is_bearish(previous)
            and _is_bullish(current)
            and current.open >= previous.close
            and current.close <= previous.open
            and current_body < previous_body
        ):
            note = "Significant bullish at bottom of trend" if context == "bottom" else "Significant only at bottom of trend"
            found.append(("Bullish Harami", Bias.NEUTRAL, note))
        if (
            _is_bullish(previous)
            and _is_bearish(current)
            and current.open <= previous.close
            and current.close >= previous.open
            and current_body < previous_body
        ):
            note = "Significant bearish at top of trend" if context == "top" else "Significant only at top of trend"
            found.append(("Bearish Harami", Bias.NEUTRAL, note))
        if current.high <= previous.high and current.low >= previous.low:
            found.append(("Mother candle", Bias.NEUTRAL, None))

    if len(candles) >= 3:
        first, middle = candles[-3], candles[-2]
        first_mid = (first.open + first.close) / 2
        # SMM Concepts 1, slide 33. Morning Star: a bearish first candle, a middle candle that opens with a
        # gap-down and whose low is below the first low, then a bullish third candle that opens with a gap-up
        # and closes above the first candle's median. Evening Star is the mirror image. The middle candle is
        # "typically" neutral and its colour does not matter, so only the gaps and extremes are checked.
        middle_gaps_down = middle.open < min(first.open, first.close) and middle.low < first.low
        middle_gaps_up = middle.open > max(first.open, first.close) and middle.high > first.high
        current_gaps_up = current.open > max(middle.open, middle.close)
        current_gaps_down = current.open < min(middle.open, middle.close)
        if _is_bearish(first) and middle_gaps_down and _is_bullish(current) and current_gaps_up and current.close > first_mid:
            if context == "top":
                found.append(("Morning Star", Bias.NEUTRAL, "Caution for bulls at top"))
            else:
                found.append(("Morning Star", Bias.BULLISH, None))
        elif _is_bullish(first) and middle_gaps_up and _is_bearish(current) and current_gaps_down and current.close < first_mid:
            if context == "bottom":
                found.append(("Evening Star", Bias.NEUTRAL, "Caution for bears at bottom"))
            else:
                found.append(("Evening Star", Bias.BEARISH, None))

        last_three = candles[-3:]
        if all(_is_bullish(c) for c in last_three) and _marching(last_three, rising=True):
            found.append(("Three White Soldiers", Bias.BULLISH, None))
        elif all(_is_bearish(c) for c in last_three) and _marching(last_three, rising=False):
            found.append(("Three Black Crows", Bias.BEARISH, None))

    # Single-candle open/close observations. A full no-wick candle is a pattern in its own right.
    observations = strong_candle_labels(current, wick_tolerance)
    if STRONG_BULLISH in observations:
        found.append((STRONG_BULLISH, Bias.BULLISH, None))
    elif STRONG_BEARISH in observations:
        found.append((STRONG_BEARISH, Bias.BEARISH, None))

    if not found:
        # A plain candle (close above or below its open) is a normal candle, per the SMM candlestick list.
        if _is_bullish(current):
            found.append(("Normal Bullish", Bias.BULLISH, None))
        elif _is_bearish(current):
            found.append(("Normal Bearish", Bias.BEARISH, None))
        else:
            return Evidence(["No special candle", *observations], Bias.NEUTRAL)

    suffix = " in Support" if at_support else " at Resistance" if at_resistance else ""
    labels = [f"{name}{suffix}" for name, _, _ in found]
    labels += [note for _, _, note in found if note]
    if STRONG_BULLISH not in observations and STRONG_BEARISH not in observations:
        labels += observations
    directional = {bias for _, bias, _ in found if bias is not Bias.NEUTRAL}
    bias = directional.pop() if len(directional) == 1 else Bias.NEUTRAL
    return Evidence(labels, bias)
