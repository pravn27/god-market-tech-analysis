from datetime import datetime, timedelta, timezone

import pytest

from god_market_api.models import Bias, Candle
from god_market_api.price_structure import (
    LocationKind,
    TrendStructure,
    detect_candle_patterns,
    dow_trend,
    find_pivots,
    locate_price,
    price_action,
)


def candle(o, h, l, c, i=0):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Candle(timestamp=start + timedelta(days=i), open=o, high=h, low=l, close=c)


def zigzag(points, step=1.0):
    """Linear path through turning points, one value per unit step."""
    values = [points[0]]
    for target in points[1:]:
        while abs(values[-1] - target) > 1e-9:
            values.append(values[-1] + (step if target > values[-1] else -step))
    return values


def series_from_path(path, spread=0.5):
    highs = [p + spread for p in path]
    lows = [p - spread for p in path]
    return highs, lows


# Pivots and Dow theory


def test_find_pivots_requires_confirmation_on_both_sides():
    highs = [1, 2, 3, 4, 5, 9, 5, 4, 3, 2, 1, 2]
    lows = [h - 1 for h in highs]
    pivot_highs, pivot_lows = find_pivots(highs, lows, left=5, right=5)
    assert [(p.index, p.price) for p in pivot_highs] == [(5, 9)]
    assert pivot_lows == []


def test_pivot_needs_right_side_candles():
    highs = [1, 2, 3, 4, 5, 9, 5, 4]
    pivot_highs, _ = find_pivots(highs, [h - 1 for h in highs], left=5, right=5)
    assert pivot_highs == []


def test_dow_trend_up_down_sideways():
    up = series_from_path(zigzag([10, 20, 15, 25, 20, 30, 25]))
    down = series_from_path(zigzag([30, 20, 25, 15, 20, 10, 15]))
    sideways = series_from_path(zigzag([10, 20, 12, 22, 14, 18, 12]))

    for (highs, lows), expected in (
        (up, TrendStructure.UP),
        (down, TrendStructure.DOWN),
        (sideways, TrendStructure.SIDEWAYS),
    ):
        pivot_highs, pivot_lows = find_pivots(highs, lows, left=3, right=3)
        result = dow_trend(pivot_highs, pivot_lows)
        assert result.structure is expected


def test_dow_trend_labels_match_worksheet_wording():
    highs, lows = series_from_path(zigzag([10, 20, 15, 25, 20, 30, 25]))
    result = dow_trend(*find_pivots(highs, lows, left=3, right=3))
    assert result.label == "HH - HL (Up Trend)"
    assert result.bias is Bias.BULLISH


def test_dow_trend_unavailable_without_two_swings_each():
    result = dow_trend([], [])
    assert result.structure is TrendStructure.UNAVAILABLE
    assert result.bias is Bias.UNAVAILABLE


# Location


def test_locate_price_near_support_and_resistance():
    highs, lows = series_from_path(zigzag([10, 20, 15, 25, 20, 30, 25]))
    pivot_highs, pivot_lows = find_pivots(highs, lows, left=3, right=3)
    # The broken 20.5 swing high now acts as support (resistance turning into support).
    near_support = locate_price(21.0, pivot_highs, pivot_lows, atr_value=1.0, proximity_atr=1.0)
    assert near_support.kind is LocationKind.NEAR_SUPPORT
    assert near_support.support == pytest.approx(20.5)
    assert near_support.resistance == pytest.approx(25.5)

    near_resistance = locate_price(24.8, pivot_highs, pivot_lows, atr_value=1.0, proximity_atr=1.0)
    assert near_resistance.kind is LocationKind.NEAR_RESISTANCE


def test_locate_price_mid_range_and_breakouts():
    highs, lows = series_from_path(zigzag([10, 20, 15, 25, 20, 30, 25]))
    pivot_highs, pivot_lows = find_pivots(highs, lows, left=3, right=3)
    assert locate_price(23.0, pivot_highs, pivot_lows, 0.5, 1.0).kind is LocationKind.MID_RANGE
    above = locate_price(35.0, pivot_highs, pivot_lows, 0.5, 1.0)
    assert above.kind is LocationKind.ABOVE_PRIOR_RESISTANCE
    assert above.resistance is None
    below = locate_price(12.0, pivot_highs, pivot_lows, 0.5, 1.0)
    assert below.kind is LocationKind.BELOW_PRIOR_SUPPORT


def test_locate_price_unavailable_without_pivots_or_atr():
    assert locate_price(10.0, [], [], 1.0, 1.0).kind is LocationKind.UNAVAILABLE
    assert locate_price(10.0, [], [], None, 1.0).kind is LocationKind.UNAVAILABLE


# Advanced Dow + price action


def test_bullish_reversal_confirmation_after_bearish_candle():
    previous = candle(110, 112, 100, 102)
    current = candle(103, 115, 102, 114)
    result = price_action(previous, current)
    assert "Close > Prev. Bearish Close" in result.labels
    assert "Close > Prev. Bearish Open" in result.labels
    assert "Close > Prev. Candle High" in result.labels
    assert "Bullish Open (above Prev. Close)" in result.labels
    assert result.bias is Bias.BULLISH


def test_bearish_reversal_confirmation_after_bullish_candle():
    previous = candle(100, 112, 98, 110)
    current = candle(109, 110, 95, 96)
    result = price_action(previous, current)
    assert "Close < Prev. Bullish Close" in result.labels
    assert "Close < Prev. Bullish Open" in result.labels
    assert "Close < Prev. Candle Low" in result.labels
    assert "Bearish Open (below Prev. Close)" in result.labels
    assert result.bias is Bias.BEARISH


def test_gap_and_strong_candle_labels():
    previous = candle(100, 105, 99, 104)
    current = candle(106, 110, 106, 110)
    result = price_action(previous, current)
    assert "Gap up" in result.labels
    assert "Strong Bullish Open (Open = Low)" in result.labels
    assert "Strong Bullish Close (Close = High)" in result.labels


def test_inside_close_is_neutral():
    previous = candle(100, 110, 95, 105)
    current = candle(105, 107, 101, 105)
    result = price_action(previous, current)
    assert result.bias is Bias.NEUTRAL


# Candlestick patterns


def test_bullish_engulf_at_support():
    candles = [candle(110, 111, 104, 105, 0), candle(104, 113, 103, 112, 1)]
    patterns = detect_candle_patterns(candles, at_support=True, at_resistance=False)
    assert patterns.labels == ["Bullish Engulf in Support"]
    assert patterns.bias is Bias.BULLISH


def test_bearish_engulf_at_resistance():
    candles = [candle(104, 111, 103, 110, 0), candle(111, 112, 102, 103, 1)]
    patterns = detect_candle_patterns(candles, at_support=False, at_resistance=True)
    assert patterns.labels == ["Bearish Engulf at Resistance"]
    assert patterns.bias is Bias.BEARISH


def test_hammer_and_hanging_man_depend_on_context():
    hammer_shape = candle(100, 101, 90, 100.8)
    falling = [candle(120 - 3 * i, 121 - 3 * i, 116 - 3 * i, 117 - 3 * i, i) for i in range(6)]
    rising = [candle(80 + 3 * i, 84 + 3 * i, 79 + 3 * i, 83 + 3 * i, i) for i in range(6)]
    assert "Hammer" in detect_candle_patterns([*falling, hammer_shape], False, False).labels
    assert "Hanging Man" in detect_candle_patterns([*rising, hammer_shape], False, False).labels


def test_inverted_hammer_doji_and_mother_candle():
    inverted = candle(100, 110, 99.8, 100.5)
    assert "Inverted Hammer" in detect_candle_patterns([inverted], False, False).labels

    doji = candle(100, 105, 95, 100.2)
    assert detect_candle_patterns([doji], False, False).labels == ["Doji"]

    mother = [candle(100, 120, 90, 115, 0), candle(110, 114, 100, 105, 1)]
    result = detect_candle_patterns(mother, False, False)
    assert "Mother candle" in result.labels


def test_piercing_patterns():
    bullish = [candle(110, 111, 99, 100, 0), candle(98, 107, 97, 106, 1)]
    assert "Bullish Piercing" in detect_candle_patterns(bullish, False, False).labels
    bearish = [candle(100, 111, 99, 110, 0), candle(112, 113, 103, 104, 1)]
    assert "Bearish Piercing" in detect_candle_patterns(bearish, False, False).labels


def test_morning_and_evening_star():
    morning = [candle(120, 121, 105, 106, 0), candle(104, 106, 102, 105, 1), candle(106, 119, 105, 118, 2)]
    assert "Morning Star" in detect_candle_patterns(morning, False, False).labels
    evening = [candle(100, 116, 99, 115, 0), candle(116, 118, 114, 117, 1), candle(115, 116, 101, 102, 2)]
    assert "Evening Star" in detect_candle_patterns(evening, False, False).labels


def test_no_special_candle():
    candles = [candle(100, 106, 99, 104, 0), candle(104, 109, 102, 107, 1)]
    result = detect_candle_patterns(candles, False, False)
    assert result.labels == ["No special candle"]
    assert result.bias is Bias.NEUTRAL
