from datetime import datetime, timedelta, timezone

import pytest

from god_market_api.models import Bias, Candle
from god_market_api.price_structure import (
    DowStructureV2Kind,
    LocationKind,
    Pivot,
    TrendStructure,
    analyze_dow_structure_v2,
    detect_candle_patterns,
    strong_candle_labels,
    dow_trend,
    find_pivots,
    locate_price,
    normalize_alternating_swings,
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


# Dow structure v2


def test_normalize_alternating_swings_retains_the_more_extreme_same_leg_pivot():
    normalized = normalize_alternating_swings(
        pivot_highs=[Pivot(1, 10), Pivot(2, 12), Pivot(5, 14)],
        pivot_lows=[Pivot(3, 6), Pivot(4, 7), Pivot(6, 9)],
    )

    assert [(s.kind.value, s.index, s.price) for s in normalized.swings] == [
        ("high", 2, 12),
        ("low", 3, 6),
        ("high", 5, 14),
        ("low", 6, 9),
    ]
    assert normalized.ambiguous_pivot_count == 0


def test_normalize_alternating_swings_omits_same_candle_high_low_as_ambiguous():
    normalized = normalize_alternating_swings(
        pivot_highs=[Pivot(1, 10), Pivot(3, 12), Pivot(5, 14)],
        pivot_lows=[Pivot(2, 6), Pivot(3, 5), Pivot(4, 7)],
    )

    assert [(s.kind.value, s.index) for s in normalized.swings] == [
        ("high", 1),
        ("low", 2),
        ("high", 5),
    ]
    assert normalized.ambiguous_pivot_count == 1


@pytest.mark.parametrize(
    ("highs", "lows", "expected", "label", "bias"),
    [
        ([Pivot(1, 10), Pivot(3, 12)], [Pivot(2, 5), Pivot(4, 7)],
         DowStructureV2Kind.UP, "HH - HL (Up Trend)", Bias.BULLISH),
        ([Pivot(1, 12), Pivot(3, 10)], [Pivot(2, 7), Pivot(4, 5)],
         DowStructureV2Kind.DOWN, "LL - LH (Down Trend)", Bias.BEARISH),
        ([Pivot(1, 12), Pivot(3, 10)], [Pivot(2, 5), Pivot(4, 7)],
         DowStructureV2Kind.CONTRACTING_RANGE, "LH - HL (Contracting Range)", Bias.NEUTRAL),
        ([Pivot(1, 10), Pivot(3, 12)], [Pivot(2, 7), Pivot(4, 5)],
         DowStructureV2Kind.EXPANDING_RANGE, "HH - LL (Expanding Range)", Bias.NEUTRAL),
        ([Pivot(1, 10), Pivot(3, 10)], [Pivot(2, 5), Pivot(4, 7)],
         DowStructureV2Kind.TRANSITION, "Equal / Transitional Structure", Bias.NEUTRAL),
    ],
)
def test_dow_v2_classifies_the_last_two_alternating_highs_and_lows(
    highs, lows, expected, label, bias
):
    result = analyze_dow_structure_v2(highs, lows, latest_close=8, atr_value=2)

    assert result.structure is expected
    assert result.label == label
    assert result.bias is bias


def test_dow_v2_distinguishes_continuation_bos_from_possible_change_of_character():
    bullish_bos = analyze_dow_structure_v2(
        [Pivot(1, 10), Pivot(3, 12)],
        [Pivot(2, 5), Pivot(4, 7)],
        latest_close=13,
        atr_value=2,
    )
    bullish_change = analyze_dow_structure_v2(
        [Pivot(1, 12), Pivot(3, 10)],
        [Pivot(2, 7), Pivot(4, 5)],
        latest_close=11,
        atr_value=2,
    )
    bearish_bos = analyze_dow_structure_v2(
        [Pivot(1, 12), Pivot(3, 10)],
        [Pivot(2, 7), Pivot(4, 5)],
        latest_close=4,
        atr_value=2,
    )
    bearish_change = analyze_dow_structure_v2(
        [Pivot(1, 10), Pivot(3, 12)],
        [Pivot(2, 5), Pivot(4, 7)],
        latest_close=6,
        atr_value=2,
    )

    assert bullish_bos.break_label == "Bullish continuation (BOS)"
    assert bullish_change.break_label == "Possible bullish change of character"
    assert bearish_bos.break_label == "Bearish continuation (BOS)"
    assert bearish_change.break_label == "Possible bearish change of character"


def test_dow_v2_atr_significance_does_not_change_structure():
    significant = analyze_dow_structure_v2(
        [Pivot(1, 10), Pivot(3, 12)],
        [Pivot(2, 5), Pivot(4, 7)],
        latest_close=8,
        atr_value=4,
        significance_atr=0.5,
    )
    minor = analyze_dow_structure_v2(
        [Pivot(1, 10), Pivot(3, 12)],
        [Pivot(2, 5), Pivot(4, 7)],
        latest_close=8,
        atr_value=10,
        significance_atr=0.5,
    )

    assert significant.structure is minor.structure is DowStructureV2Kind.UP
    assert significant.structural_moves_significant is True
    assert minor.structural_moves_significant is False


def test_dow_v2_is_unavailable_without_two_normalized_swings_of_each_kind():
    result = analyze_dow_structure_v2(
        [Pivot(1, 10)],
        [Pivot(2, 5)],
        latest_close=7,
        atr_value=1,
    )

    assert result.structure is DowStructureV2Kind.UNAVAILABLE
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
    # Strong-candle labels now belong to the candlestick row, not the price action row.
    assert not any("Strong" in label for label in result.labels)
    assert strong_candle_labels(current) == [
        "Strong Bullish Open (Open = Low)",
        "Strong Bullish Close (Close = High)",
        "Strong Bullish Candle (no upper & lower wicks)",
    ]
    patterns = detect_candle_patterns([previous, current], False, False)
    assert "Strong Bullish Candle (no upper & lower wicks)" in patterns.labels
    assert patterns.bias is Bias.BULLISH


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
    assert "Bearish Piercing (Dark Cloud Cover)" in detect_candle_patterns(bearish, False, False).labels


def test_morning_and_evening_star():
    morning = [candle(120, 121, 105, 106, 0), candle(104, 106, 102, 105, 1), candle(106, 119, 105, 118, 2)]
    assert "Morning Star" in detect_candle_patterns(morning, False, False).labels
    evening = [candle(100, 116, 99, 115, 0), candle(116, 118, 114, 117, 1), candle(115, 116, 101, 102, 2)]
    assert "Evening Star" in detect_candle_patterns(evening, False, False).labels


def test_morning_star_needs_the_gap_and_low_rules_from_smm():
    # SMM Concepts 1, slide 33: the middle candle opens with a gap-down and its low is below the first low.
    middle_opens_above_first_close = [
        candle(120, 121, 105, 106, 0), candle(106.5, 107, 104, 106, 1), candle(107, 119, 106, 118, 2),
    ]
    assert "Morning Star" not in detect_candle_patterns(middle_opens_above_first_close, False, False).labels
    # The third candle must open with a gap-up above the middle candle.
    no_gap_up_on_third = [
        candle(120, 121, 105, 106, 0), candle(104, 106, 102, 105, 1), candle(104.5, 119, 103, 118, 2),
    ]
    assert "Morning Star" not in detect_candle_patterns(no_gap_up_on_third, False, False).labels
    # The middle candle's low must be lower than the first candle's low.
    middle_low_not_below_first = [
        candle(120, 121, 105, 106, 0), candle(104, 106, 105.5, 105, 1), candle(106, 119, 105, 118, 2),
    ]
    assert "Morning Star" not in detect_candle_patterns(middle_low_not_below_first, False, False).labels


def test_plain_candles_are_normal_bullish_or_bearish():
    candles = [candle(100, 106, 99, 104, 0), candle(104, 109, 102, 107, 1)]
    result = detect_candle_patterns(candles, False, False)
    assert result.labels == ["Normal Bullish"]
    assert result.bias is Bias.BULLISH
    bearish = detect_candle_patterns([candle(100, 101, 95, 96)], False, False)
    assert bearish.labels == ["Normal Bearish"]
    assert bearish.bias is Bias.BEARISH


def test_no_special_candle_only_when_there_is_no_range():
    result = detect_candle_patterns([candle(100, 100, 100, 100)], False, False)
    assert result.labels == ["No special candle"]
    assert result.bias is Bias.NEUTRAL


def test_engulf_at_top_is_not_significantly_bullish_and_neutral():
    candles = [candle(110, 111, 104, 105, 0), candle(104, 113, 103, 112, 1)]
    result = detect_candle_patterns(candles, at_support=False, at_resistance=True)
    assert result.labels == ["Bullish Engulf at Resistance", "Not significantly bullish at top"]
    assert result.bias is Bias.NEUTRAL


def test_inverted_hammer_at_bottom_is_not_significantly_bearish():
    inverted = candle(100, 110, 99.8, 100.5)
    result = detect_candle_patterns([inverted], at_support=True, at_resistance=False)
    assert "Inverted Hammer in Support" in result.labels
    assert "Not significantly bearish at bottom" in result.labels
    assert result.bias is Bias.NEUTRAL
    at_top = detect_candle_patterns([inverted], at_support=False, at_resistance=True)
    assert at_top.bias is Bias.BEARISH
    # PAPA: ignored in the middle of a trend or range.
    mid_trend = detect_candle_patterns([inverted], at_support=False, at_resistance=False)
    assert "Inverted Hammer" in mid_trend.labels
    assert "Ignore mid-trend" in mid_trend.labels
    assert mid_trend.bias is Bias.NEUTRAL


def test_hammer_in_the_middle_of_a_trend_is_ignored():
    hammer = candle(100, 101, 90, 100.8)
    mid_trend = detect_candle_patterns([hammer], at_support=False, at_resistance=False)
    assert "Hammer" in mid_trend.labels
    assert "Ignore mid-trend" in mid_trend.labels
    assert mid_trend.bias is Bias.NEUTRAL
    falling = [candle(100 - 2 * i, 101 - 2 * i, 98 - 2 * i, 99 - 2 * i, i) for i in range(6)]
    at_bottom = detect_candle_patterns([*falling, hammer], at_support=False, at_resistance=False)
    assert at_bottom.bias is Bias.BULLISH


def test_high_wave_is_neutral_with_big_wicks_on_both_sides():
    high_wave = candle(100, 110, 90, 103)
    result = detect_candle_patterns([high_wave], False, False)
    assert result.labels == ["High Wave"]
    assert result.bias is Bias.NEUTRAL


def test_bullish_and_bearish_harami_are_neutral_with_location_note():
    bullish_harami = [candle(110, 111, 99, 100, 0), candle(101, 106, 100, 105, 1)]
    result = detect_candle_patterns(bullish_harami, at_support=True, at_resistance=False)
    assert "Bullish Harami in Support" in result.labels
    assert "Significant bullish at bottom of trend" in result.labels
    assert result.bias is Bias.NEUTRAL
    bearish_harami = [candle(100, 111, 99, 110, 0), candle(109, 109.5, 104, 105, 1)]
    result = detect_candle_patterns(bearish_harami, at_support=False, at_resistance=True)
    assert "Bearish Harami at Resistance" in result.labels
    assert "Significant bearish at top of trend" in result.labels
    assert result.bias is Bias.NEUTRAL


def test_morning_star_at_top_is_caution_for_bulls():
    morning = [candle(110, 111, 95, 96, 0), candle(95.5, 96, 94, 95.8, 1), candle(97, 106, 96.5, 105, 2)]
    result = detect_candle_patterns(morning, at_support=False, at_resistance=True)
    assert "Morning Star at Resistance" in result.labels
    assert "Caution for bulls at top" in result.labels
    assert result.bias is Bias.NEUTRAL


def test_evening_star_at_bottom_is_caution_for_bears():
    evening = [candle(90, 106, 89, 105, 0), candle(105.5, 107, 105, 105.2, 1), candle(104, 105, 92, 93, 2)]
    result = detect_candle_patterns(evening, at_support=True, at_resistance=False)
    assert "Evening Star in Support" in result.labels
    assert "Caution for bears at bottom" in result.labels
    assert result.bias is Bias.NEUTRAL


def test_open_only_observation_does_not_suppress_the_normal_candle():
    candles = [candle(100, 106, 99, 104, 0), candle(100, 110, 100, 108, 1)]
    result = detect_candle_patterns(candles, False, False)
    assert result.labels[0] == "Normal Bullish"
    assert "Strong Bullish Open (Open = Low)" in result.labels
    assert "Strong Bullish Candle (no upper & lower wicks)" not in result.labels
