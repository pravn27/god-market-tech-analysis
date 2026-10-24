"""Significant candle evidence for the latest candle (PAPA Seminar key points, sheet "Significant candles").

A significant candle is a candle that closes beyond the previous candle's High or Low, breaks a confirmed swing
level, or gaps through one. The latest candle is then checked against the recent significant candles, the levels,
the gaps, the location, the candlestick patterns, the Dow confirmation, Bollinger, RSI and volume.
Group B items (3WS/3BC, counter attacks, sandwich, rounding, FBO/FBD, shakeouts, Ungli) are not evaluated here.
"""

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from .models import Bias, Candle
from .price_structure import Evidence, Pivot

SIGNIFICANT_LOOKBACK = 20
NO_EVENT_LABEL = "No significant candle event"


@dataclass(frozen=True)
class SignificantCandle:
    index: int
    direction: int  # +1 bullish, -1 bearish
    high: float
    low: float


def _confirmed_prices(pivots: Sequence[Pivot], index: int, window: int) -> List[float]:
    """Swing prices confirmed before ``index`` (a pivot needs ``window`` candles on its right)."""
    return [pivot.price for pivot in pivots if pivot.index + window < index]


def _significance(candles: Sequence[Candle], index: int, highs: Sequence[float], lows: Sequence[float]) -> int:
    current, previous = candles[index], candles[index - 1]
    if current.close > previous.high:
        return 1
    if current.close < previous.low:
        return -1
    if any(previous.close <= level < current.close for level in highs):
        return 1
    if any(current.close < level <= previous.close for level in lows):
        return -1
    if current.low > previous.high and any(previous.high <= level < current.low for level in highs):
        return 1
    if current.high < previous.low and any(current.high < level <= previous.low for level in lows):
        return -1
    return 0


def find_significant_candles(
    candles: Sequence[Candle],
    pivot_highs: Sequence[Pivot],
    pivot_lows: Sequence[Pivot],
    window: int,
    lookback: int = SIGNIFICANT_LOOKBACK,
) -> List[SignificantCandle]:
    """Significant candles among the ``lookback`` candles before the latest one (oldest first)."""
    found: List[SignificantCandle] = []
    last = len(candles) - 1
    for index in range(max(1, last - lookback), last):
        highs = _confirmed_prices(pivot_highs, index, window)
        lows = _confirmed_prices(pivot_lows, index, window)
        direction = _significance(candles, index, highs, lows)
        if direction:
            found.append(SignificantCandle(index, direction, candles[index].high, candles[index].low))
    return found


def _has_pattern(labels: Sequence[str], name: str) -> bool:
    for label in labels:
        if name == "Hammer" and "Inverted Hammer" in label:
            continue
        if name in label:
            return True
    return False


def _direction(bias: Bias) -> int:
    return 1 if bias is Bias.BULLISH else -1 if bias is Bias.BEARISH else 0


def _bollinger_labels(labels: Sequence[str]) -> List[Tuple[str, int]]:
    found: List[Tuple[str, int]] = []
    for label in labels:
        if "BKT" in label:
            found.append(("BKT candle (upper band failure)", -1))
        elif "BKP" in label:
            found.append(("BKP candle (lower band failure)", 1))
        elif "UBBC" in label and "Failure" in label:
            found.append(("BB challenge failing candle (upper)", -1))
        elif "LBBC" in label and "Failure" in label:
            found.append(("BB challenge failing candle (lower)", 1))
        elif "UBBC" in label:
            found.append(("BB challenge candle (upper)", 1))
        elif "LBBC" in label:
            found.append(("BB challenge candle (lower)", -1))
    return found


def significant_candle_evidence(
    candles: Sequence[Candle],
    pivot_highs: Sequence[Pivot],
    pivot_lows: Sequence[Pivot],
    window: int,
    *,
    at_support: bool,
    at_resistance: bool,
    pattern_labels: Sequence[str],
    action_labels: Mapping[str, Bias],
    bollinger_labels: Sequence[str],
    rsi_now: Optional[float],
    rsi_prev: Optional[float],
    volume_ratio: Optional[float],
    volume_threshold: float,
    lookback: int = SIGNIFICANT_LOOKBACK,
) -> Tuple[Evidence, Dict[str, Optional[float]]]:
    """Evidence for the latest candle (needs at least three candles) and the stop-loss reference values."""
    index = len(candles) - 1
    current, previous = candles[index], candles[index - 1]
    highs = _confirmed_prices(pivot_highs, index, window)
    lows = _confirmed_prices(pivot_lows, index, window)
    significant = find_significant_candles(candles, pivot_highs, pivot_lows, window, lookback)
    found: List[Tuple[str, int]] = []
    values: Dict[str, Optional[float]] = {}

    # Takes out / BO / BD of recent significant candles: the newest matching candle for each kind.
    seen_kinds = set()
    for candle_info in reversed(significant):
        ago = index - candle_info.index
        checks = [
            ("takes_high", current.high > candle_info.high, f"Takes out high of significant candle {candle_info.high:,.2f} ({ago} candles ago)", 1),
            ("takes_low", current.low < candle_info.low, f"Takes out low of significant candle {candle_info.low:,.2f} ({ago} candles ago)", -1),
            ("bo", current.close > candle_info.high, f"BO of significant candle {candle_info.high:,.2f} ({ago} candles ago)", 1),
            ("bd", current.close < candle_info.low, f"BD of significant candle {candle_info.low:,.2f} ({ago} candles ago)", -1),
        ]
        for kind, hit, label, direction in checks:
            if hit and kind not in seen_kinds:
                seen_kinds.add(kind)
                found.append((label, direction))

    # Breaks of confirmed levels by the latest candle (nearest level first).
    breaks_up = [level for level in highs if previous.close <= level < current.close]
    if breaks_up:
        found.append((f"Breaks out resistance {min(breaks_up):,.2f}", 1))
    breaks_down = [level for level in lows if current.close < level <= previous.close]
    if breaks_down:
        found.append((f"Breaks down support {max(breaks_down):,.2f}", -1))

    # Gaps through confirmed levels: highest resistance cleared, lowest support broken.
    gap_up_levels = [level for level in highs if previous.high <= level < current.low]
    if current.low > previous.high and gap_up_levels:
        found.append((f"Gap up through resistance {max(gap_up_levels):,.2f}", 1))
    gap_down_levels = [level for level in lows if current.high < level <= previous.low]
    if current.high < previous.low and gap_down_levels:
        found.append((f"Gap down through support {min(gap_down_levels):,.2f}", -1))

    # Exhaustion gap fill: the newest unfilled gap of each direction that the latest candle reaches back into.
    filled_kinds = set()
    for j in range(index - 1, max(0, index - lookback) - 1, -1):
        if j < 1:
            break
        before, gap_bar = candles[j - 1], candles[j]
        if gap_bar.low > before.high and "up" not in filled_kinds:
            gap_low, gap_high = before.high, gap_bar.low
            if not any(candles[k].low <= gap_low for k in range(j + 1, index)) and current.low <= gap_low:
                filled_kinds.add("up")
                found.append((f"Fills exhaustion gap up {gap_low:,.2f}-{gap_high:,.2f}", 0))
        if gap_bar.high < before.low and "down" not in filled_kinds:
            gap_low, gap_high = gap_bar.high, before.low
            if not any(candles[k].high >= gap_high for k in range(j + 1, index)) and current.high >= gap_high:
                filled_kinds.add("down")
                found.append((f"Fills exhaustion gap down {gap_low:,.2f}-{gap_high:,.2f}", 0))

    # Stop-loss reference: the newest significant candle (PAPA: stop below a breakout candle low, above a breakdown high).
    if significant:
        latest = significant[-1]
        values["stop_reference_high"] = latest.high
        values["stop_reference_low"] = latest.low
        values["stop_reference_bars_ago"] = float(index - latest.index)
        found.append((f"Stop reference: significant candle high {latest.high:,.2f}, low {latest.low:,.2f}", 0))

    # Location with candlestick patterns (SMM / PAPA candle list).
    if at_support:
        for name in ("Morning Star", "Bullish Engulf", "Hammer", "Inverted Hammer"):
            if _has_pattern(pattern_labels, name):
                found.append((f"{name} at major support", 1))
    if at_resistance:
        for name in ("Evening Star", "Bearish Engulf", "Inverted Hammer", "Hanging Man"):
            if _has_pattern(pattern_labels, name):
                found.append((f"{name} at major resistance", -1))

    # Dow reversal / continuation confirmation from the price action row.
    for label, bias in action_labels.items():
        if label.startswith("Reversal Confirmation"):
            found.append(("Dow reversal confirmation candle", _direction(bias)))
        if "trend continues" in label:
            found.append(("Dow continuation confirmation candle", _direction(bias)))

    found.extend(_bollinger_labels(bollinger_labels))

    if rsi_now is not None and rsi_prev is not None:
        if rsi_prev <= 40 < rsi_now:
            found.append(("RSI brought above 40", 1))
        if rsi_prev >= 60 > rsi_now:
            found.append(("RSI brought below 60", -1))

    # High volume: on a breakout or breakdown of the same direction, or at a major top or bottom (neutral).
    if volume_ratio is not None and volume_ratio >= volume_threshold:
        breakout_directions = {
            direction
            for label, direction in found
            if label.startswith(("BO of", "BD of", "Takes out", "Breaks", "Gap up through", "Gap down through"))
        }
        if len(breakout_directions) == 1:
            direction = next(iter(breakout_directions))
            found.append(("High volume breakout" if direction > 0 else "High volume breakdown", direction))
        if at_support:
            found.append(("High volume at major support", 0))
        if at_resistance:
            found.append(("High volume at major resistance", 0))

    if not found:
        return Evidence([NO_EVENT_LABEL], Bias.NEUTRAL, {NO_EVENT_LABEL: Bias.NEUTRAL}), values

    labels: List[str] = []
    label_biases: Dict[str, Bias] = {}
    for label, direction in found:
        if label in label_biases:
            continue
        labels.append(label)
        label_biases[label] = Bias.BULLISH if direction > 0 else Bias.BEARISH if direction < 0 else Bias.NEUTRAL
    up = any(direction > 0 for _, direction in found)
    down = any(direction < 0 for _, direction in found)
    bias = Bias.BULLISH if up and not down else Bias.BEARISH if down and not up else Bias.NEUTRAL
    return Evidence(labels, bias, label_biases), values
