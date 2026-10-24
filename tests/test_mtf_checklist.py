from datetime import datetime, timedelta, timezone

import pytest

from god_market_api.models import Bias, Candle
from god_market_api.mtf_checklist import (
    CHECKLIST_ROWS,
    ChecklistThresholds,
    _breakout_labels,
    _divergence_labels,
    _fibonacci_labels,
    adx_cell,
    divergence_cell,
    divergence_pivots,
    bollinger_cell,
    chart_pattern_cell,
    dmi_cell,
    ema_cell,
    evaluate_timeframe,
    heikin_ashi_labels,
    macd_cell,
    rsi_cell,
    stochastic_cell,
    volume_cell,
)
from god_market_api.price_structure import Pivot, detect_candle_patterns, find_pivots

T = ChecklistThresholds()


def pad(values, size=60):
    """Left-pad a short series so lookbacks exist without changing the tail."""
    return [values[0]] * (size - len(values)) + list(values)


# Bollinger Band


def bb_case(highs, lows, closes, upper, basis, lower):
    return bollinger_cell(pad(highs), pad(lows), pad(closes), pad(upper), pad(basis), pad(lower), T)


def test_ubbc_bb_expands():
    cell = bb_case([100, 101, 103, 106], [95] * 4, [99, 100, 102, 105.5], [104, 104, 104.5, 106], [100] * 4, [96, 96, 95.5, 94])
    assert cell.labels[0] == "UBBC, BB Expands"
    assert cell.bias is Bias.BULLISH
    assert "Bands Expanding" in cell.labels


def test_lbbc_bb_expands():
    cell = bb_case([100] * 4, [97, 96, 95, 93], [98, 97, 96, 93.5], [104, 104, 104.5, 106], [100] * 4, [96, 96, 95.5, 94])
    assert cell.labels[0] == "LBBC, BB Expands"
    assert cell.bias is Bias.BEARISH


def test_ubbc_failure_bkt():
    cell = bb_case([103, 104.5, 102, 102], [98] * 4, [102, 103, 101, 101], [104] * 4, [100] * 4, [96] * 4)
    assert cell.labels[0] == "UBBC Failure, BKT"
    assert cell.bias is Bias.BEARISH
    assert "Bands are Flat" in cell.labels


def test_lbbc_failure_bkp():
    cell = bb_case([102] * 4, [97, 95.5, 98, 98], [98, 97, 99, 99], [104] * 4, [100] * 4, [96] * 4)
    assert cell.labels[0] == "LBBC Failure, BKP"
    assert cell.bias is Bias.BULLISH


def test_bb_median_relation():
    above = bb_case([103] * 4, [101] * 4, [102.5] * 4, [104] * 4, [100] * 4, [96] * 4)
    near = bb_case([101] * 4, [99] * 4, [100.3] * 4, [104] * 4, [100] * 4, [96] * 4)
    below = bb_case([99] * 4, [97] * 4, [97.5] * 4, [104] * 4, [100] * 4, [96] * 4)
    assert (above.labels[0], above.bias) == ("Price is Above Median", Bias.BULLISH)
    assert (near.labels[0], near.bias) == ("Price is Near Median", Bias.NEUTRAL)
    assert (below.labels[0], below.bias) == ("Price is Below Median", Bias.BEARISH)


def test_bb_unavailable_without_bands():
    cell = bollinger_cell([1.0], [1.0], [1.0], [None], [None], [None], T)
    assert cell.bias is Bias.UNAVAILABLE
    assert "23 candles" in cell.unavailable_reason


# RSI


@pytest.mark.parametrize(
    "value,label,bias",
    [
        (85, "> 80, Unsustainable for Bulls", Bias.BULLISH),
        (65, "> 60, Bullish Momentum", Bias.BULLISH),
        (52, "Near 50", Bias.NEUTRAL),
        (42, "Swing zone (40 - 60), Below 50", Bias.NEUTRAL),
        (58, "Swing zone (40 - 60), Above 50", Bias.NEUTRAL),
        (35, "< 40, Bearish Momentum", Bias.BEARISH),
        (15, "< 20, Unsustainable for Bears", Bias.BEARISH),
    ],
)
def test_rsi_zones(value, label, bias):
    cell = rsi_cell(pad([value] * 4), T)
    assert cell.labels[0] == label
    assert cell.labels[1] == f"RSI {value:.2f}"
    assert cell.bias is bias


def test_rsi_recent_crossings():
    assert "Crossing above 60" in rsi_cell(pad([55, 58, 61, 62]), T).labels
    assert "Crossing below 40" in rsi_cell(pad([45, 42, 39, 38]), T).labels
    assert "Crossing above 40" in rsi_cell(pad([35, 38, 41, 43]), T).labels
    assert "Crossing below 60" in rsi_cell(pad([65, 62, 59, 57]), T).labels


# DMI / ADX


def test_dmi_direction_spread_and_crossover():
    bullish = dmi_cell(pad([18, 20, 23, 26]), pad([22, 21, 20, 18]), T)
    assert bullish.labels[:2] == ["+DI > -DI", "Expanding"]
    assert "PCO" in bullish.labels
    assert bullish.bias is Bias.BULLISH

    bearish = dmi_cell(pad([15, 16, 17, 18]), pad([30, 28, 25, 22]), T)
    assert bearish.labels[:2] == ["-DI > +DI", "Contracting"]
    assert bearish.bias is Bias.BEARISH


@pytest.mark.parametrize(
    "series,expected_band",
    [
        ([8, 8.5, 9, 9.5], "No Momentum (< 10)"),
        ([10, 10.5, 11, 11.5], "Momentum Building (10 - 12)"),
        ([12, 12.5, 13, 13.5], "Good Momentum (12 - 14)"),
        ([20, 22, 24, 26], "Excellent Momentum (> 14)"),
        ([50, 54, 57, 60], "Unsustainable (> 55)"),
    ],
)
def test_adx_bands(series, expected_band):
    cell = adx_cell(pad(series), pad([25] * 4), pad([15] * 4), T)
    assert expected_band in cell.labels


def test_adx_label_shows_the_current_value():
    cell = adx_cell(pad([20, 22, 24, 26.5]), pad([25] * 4), pad([15] * 4), T)
    assert cell.labels[-1] == "ADX 26.50"
    assert cell.values["adx"] == 26.5


def test_adx_rising_follows_dmi_and_falling_is_neutral():
    rising = adx_cell(pad([18, 19, 20, 22]), pad([25] * 4), pad([15] * 4), T)
    assert rising.labels[0] == "Raising > 12 (Gaining good strength in Trend)"
    assert rising.bias is Bias.BULLISH

    falling = adx_cell(pad([22, 20, 19, 18]), pad([25] * 4), pad([15] * 4), T)
    assert falling.labels[0] == "Falling (Losing strength in Trend)"
    assert falling.bias is Bias.NEUTRAL


# MACD


def macd_case(line, signal):
    return macd_cell(pad(line), pad(signal), T)


def test_macd_recent_nco_sell_above_zero():
    cell = macd_case([50, 52, 51, 48], [45, 48, 50, 49.5])
    assert cell.labels[0] == "(NCO) Sell Signal above Zero Line"
    assert "NCO state" in cell.labels and "Down Tick" in cell.labels
    assert cell.bias is Bias.BEARISH


def test_macd_recent_pco_buy_below_zero():
    cell = macd_case([-50, -48, -45, -40], [-44, -44, -44, -42])
    assert cell.labels[0] == "(PCO) Buy Signal below Zero Line"
    assert cell.bias is Bias.BULLISH


def test_macd_buy_signal_without_recent_crossover():
    cell = macd_case(pad([-30, -25, -20, -15, -10, -8], 10), pad([-40, -36, -32, -28, -24, -20], 10))
    assert cell.labels[0] == "Buy Signal below Zero Line"
    assert cell.bias is Bias.BULLISH


def test_macd_near_zero_and_not_clear():
    line = [40, -40, 30, -30, 20, 10, 5, 4, 3.5, 3.8]
    signal = [35, -35, 25, -25, 15, 2, 2.5, 3, 3.6, 3.7]
    cell = macd_case(line, signal)
    assert cell.labels[0].endswith("near Zero Line")

    mixed = macd_case(pad([10, 12, 14, 13], 10), pad([5, 6, 7, 8], 10))
    assert mixed.labels[0].startswith("Not Clear")
    assert mixed.bias is Bias.NEUTRAL


# Stochastic


def stoch_case(k, d):
    return stochastic_cell(pad(k), pad(d), T)


def test_stochastic_buy_from_oversold():
    cell = stoch_case([12, 10, 14, 18], [15, 13, 12, 14])
    assert cell.labels[0] == "(< 20) Buy Signal from OverSold (10 - 20)"
    assert cell.labels[1] == "%K 18.00 / %D 14.00"
    assert cell.bias is Bias.BULLISH


def test_stochastic_sell_from_overbought():
    cell = stoch_case([86, 88, 84, 82], [83, 85, 86, 85])
    assert cell.labels[0] == "(> 80) NCO Sell Signal from OverBought (80 - 90)"
    assert cell.bias is Bias.BEARISH


def test_stochastic_pco_near_80_up_tick():
    cell = stoch_case([66, 70, 74, 78], [70, 71, 72, 74])
    assert cell.labels[0] == "(Near 80) PCO Buy Signal Up tick"


def test_stochastic_not_clear_without_crossover():
    cell = stoch_case(pad([50, 52, 54, 55], 10), pad([45, 47, 49, 50], 10))
    assert cell.labels[0] == "Not Clear"
    assert "Up tick" in cell.labels
    assert cell.bias is Bias.NEUTRAL


# EMAs


def test_ema_bullish_stack_and_price_relations():
    emas = {5: pad([108] * 4), 13: pad([105] * 4), 26: pad([103] * 4), 50: pad([100] * 4),
            100: pad([98] * 4), 150: pad([96] * 4), 200: pad([94] * 4)}
    cell = ema_cell(pad([110] * 4), emas, T)
    assert cell.labels[:7] == [
        "Price > 5", "Price > 13", "Price > 26", "Price > 50", "Price > 100", "Price > 150", "Price > 200"
    ]
    assert "POC, 5 > 13 > 26" in cell.labels
    assert "POC, 100 > 150 > 200" in cell.labels
    assert cell.bias is Bias.BULLISH


def test_ema_bearish_stack_and_recent_crossover():
    emas = {5: pad([101, 100, 98, 96]), 13: pad([99, 99, 99, 99]), 26: pad([100] * 4), 50: pad([104] * 4)}
    cell = ema_cell(pad([95] * 4), emas, T)
    assert "NOC, 5 < 13 < 26" in cell.labels
    assert "5 EMA NCO with 13 EMA" in cell.labels
    assert cell.bias is Bias.BEARISH
    assert cell.values["ema_200"] is None


def test_ema_intermingled_is_neutral():
    emas = {5: pad([101] * 4), 13: pad([102] * 4), 26: pad([100] * 4), 50: pad([99] * 4)}
    cell = ema_cell(pad([101.5] * 4), emas, T)
    assert "EMAs intermingled" in cell.labels
    assert cell.bias is Bias.NEUTRAL


def test_ema_steep_upward_stack_is_green_and_labelled():
    emas = {5: pad([100, 102, 104, 106]), 13: pad([99, 100.5, 102, 103.5]),
            26: pad([96, 97.5, 99, 100.5]), 50: pad([92, 94, 96, 98])}
    cell = ema_cell(pad([107] * 4), emas, T)
    assert "POC, 5 > 13 > 26" in cell.labels
    assert "Steep upward EMAs: 5, 13, 26, 50" in cell.labels
    assert cell.bias is Bias.BULLISH
    assert cell.values["ema_5_slope_pct"] == pytest.approx(6.0, abs=0.01)


def test_ema_steep_downward_stack_is_red_and_labelled():
    emas = {5: pad([100, 98, 96, 94]), 13: pad([101, 99, 97.5, 96.5]),
            26: pad([104, 102, 100.5, 99.5]), 50: pad([108, 106, 104, 102])}
    cell = ema_cell(pad([93] * 4), emas, T)
    assert "NOC, 5 < 13 < 26" in cell.labels
    assert "Steep downward EMAs: 5, 13, 26, 50" in cell.labels
    assert cell.bias is Bias.BEARISH


def test_ema_flat_lines_are_labelled_flat_and_colour_follows_pco_state():
    emas = {5: pad([103] * 4), 13: pad([102] * 4), 26: pad([101] * 4), 50: pad([100] * 4)}
    cell = ema_cell(pad([99] * 4), emas, T)
    assert "Flat EMAs: 5, 13, 26, 50" in cell.labels
    assert "EMAs intermingled" not in cell.labels
    # Colour follows the 5 > 13 > 26 stack, not the price relation to the 50 EMA.
    assert cell.bias is Bias.BULLISH


def test_ema_intermingled_flat_lines_report_both_states():
    emas = {5: pad([101] * 4), 13: pad([102] * 4), 26: pad([100] * 4), 50: pad([99] * 4)}
    cell = ema_cell(pad([101.5] * 4), emas, T)
    assert "EMAs intermingled" in cell.labels
    assert "Flat EMAs: 5, 13, 26, 50" in cell.labels
    assert cell.bias is Bias.NEUTRAL


def test_ema_short_group_flat_and_long_group_upward_are_listed_per_line():
    emas = {5: pad([103] * 4), 13: pad([102] * 4), 26: pad([101] * 4), 50: pad([100] * 4),
            100: pad([100, 100.5, 100.8, 101]), 150: pad([150, 150.6, 151.2, 151.5]),
            200: pad([200, 200.6, 201, 201.5])}
    cell = ema_cell(pad([102] * 4), emas, T)
    assert "Flat EMAs: 5, 13, 26, 50" in cell.labels
    assert "Upward EMAs: 100, 150, 200" in cell.labels
    assert not any(label.startswith("Downward") or label.startswith("Steep") for label in cell.labels)
    assert cell.values["ema_100_trend"] == "up"
    assert cell.values["ema_200_trend"] == "up"


def test_ema_long_group_downward_is_listed_per_line():
    emas = {5: pad([103] * 4), 13: pad([102] * 4), 26: pad([101] * 4), 50: pad([100] * 4),
            100: pad([101, 100.5, 100.2, 100]), 150: pad([152, 151.4, 150.8, 150.2]),
            200: pad([202, 201.5, 201, 200.5])}
    cell = ema_cell(pad([102] * 4), emas, T)
    assert "Downward EMAs: 100, 150, 200" in cell.labels
    assert cell.values["ema_150_trend"] == "down"


# Whole timeframe


def make_candles(n=300):
    start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    candles = []
    price = 100.0
    for i in range(n):
        drift = 0.6 if (i // 20) % 2 == 0 else -0.4
        open_ = price
        close = price + drift
        candles.append(Candle(timestamp=start + timedelta(days=i), open=open_, high=max(open_, close) + 0.5,
                              low=min(open_, close) - 0.5, close=close, volume=1000 + 50 * (i % 7)))
        price = close
    return candles


def test_dow_v2_row_is_additive_and_immediately_follows_the_v1_row():
    row_ids = [row.id for row in CHECKLIST_ROWS]

    assert row_ids[row_ids.index("dow_trend") + 1] == "dow_structure_v2"


def test_dow_v2_excludes_only_the_latest_live_candle():
    candles = make_candles()

    closed = evaluate_timeframe(candles, T, latest_candle_live=False)
    with_live = evaluate_timeframe(candles, T, latest_candle_live=True)

    closed_v2 = closed.cells["dow_structure_v2"]
    live_v2 = with_live.cells["dow_structure_v2"]
    assert closed_v2.values["used_closed_candles"] == len(candles)
    assert closed_v2.values["excluded_live_candle"] is False
    assert live_v2.values["used_closed_candles"] == len(candles) - 1
    assert live_v2.values["excluded_live_candle"] is True
    assert live_v2.values["latest_closed_candle_at"] == candles[-2].timestamp.isoformat()
    assert with_live.cells["dow_trend"] == closed.cells["dow_trend"]


def test_dow_v2_exposes_structure_break_significance_and_swing_evidence():
    cell = evaluate_timeframe(make_candles(), T).cells["dow_structure_v2"]

    assert cell.labels
    assert cell.rule_ids == ["dow-v2", "dow-v2-break", "dow-v2-significance"]
    assert cell.values["confirmation_lag_bars"] == T.pivot_window
    assert "previous_swing_high_at" in cell.values
    assert "last_swing_low_at" in cell.values
    assert "structural_moves_significant" in cell.values


def test_evaluate_timeframe_fills_every_automated_row():
    evaluation = evaluate_timeframe(make_candles(), T)
    automated = [row.id for row in CHECKLIST_ROWS if row.automated]
    assert set(automated) <= set(evaluation.cells)
    for row_id in automated:
        cell = evaluation.cells[row_id]
        assert cell.labels, row_id
        assert cell.unavailable_reason is None, row_id
    assert evaluation.last_close == pytest.approx(make_candles()[-1].close)


def test_evaluate_timeframe_marks_everything_unavailable_for_bad_candles():
    evaluation = evaluate_timeframe([], T)
    for row in CHECKLIST_ROWS:
        if row.automated:
            assert evaluation.cells[row.id].bias is Bias.UNAVAILABLE
            assert evaluation.cells[row.id].unavailable_reason == "No candles were returned."


def test_short_history_makes_only_long_indicators_unavailable():
    evaluation = evaluate_timeframe(make_candles(60), T)
    assert evaluation.cells["rsi"].bias is not Bias.UNAVAILABLE
    assert evaluation.cells["emas"].values["ema_200"] is None


# Evidence inside existing rows


def bar(o, h, l, c, volume=None, i=0):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return Candle(timestamp=start + timedelta(days=i), open=o, high=h, low=l, close=c, volume=volume)


def close_path(closes, volume=None):
    return [bar(c, c + 0.5, c - 0.5, c, volume=volume, i=i) for i, c in enumerate(closes)]


def test_bearish_divergence_when_price_makes_higher_high_on_lower_oscillator():
    highs = [Pivot(10, 100.0), Pivot(50, 105.0)]
    oscillator = [None] * 60
    oscillator[10], oscillator[50] = 70.0, 60.0
    assert _divergence_labels("RSI", highs, [], oscillator, 60, T) == ["Bearish divergence (RSI)"]


def test_bullish_divergence_when_price_makes_lower_low_on_higher_oscillator():
    lows = [Pivot(10, 95.0), Pivot(50, 90.0)]
    oscillator = [None] * 60
    oscillator[10], oscillator[50] = 30.0, 35.0
    assert _divergence_labels("MACD", [], lows, oscillator, 60, T) == ["Bullish divergence (MACD)"]


def test_no_divergence_when_oscillator_confirms_price():
    highs = [Pivot(10, 100.0), Pivot(50, 105.0)]
    oscillator = [None] * 60
    oscillator[10], oscillator[50] = 60.0, 70.0
    assert _divergence_labels("RSI", highs, [], oscillator, 60, T) == []


def test_divergence_ignores_swings_older_than_the_lookback():
    highs = [Pivot(5, 100.0), Pivot(20, 105.0)]
    oscillator = [None] * 100
    oscillator[5], oscillator[20] = 70.0, 60.0
    assert _divergence_labels("RSI", highs, [], oscillator, 100, T) == []


def test_divergence_row_collects_labels_from_all_three_oscillators_neutrally():
    highs = [Pivot(10, 100.0), Pivot(50, 105.0)]
    lows = [Pivot(12, 95.0), Pivot(52, 90.0)]
    rsi = [None] * 60
    rsi[10], rsi[50] = 70.0, 60.0  # bearish: higher high, lower RSI
    macd = [None] * 60
    macd[12], macd[52] = 30.0, 35.0  # bullish: lower low, higher MACD
    stoch = [None] * 60
    cell = divergence_cell((("RSI", rsi), ("MACD", macd), ("Stochastic %K", stoch)), highs, lows, 60, T)
    assert cell.labels == ["Bearish divergence (RSI)", "Bullish divergence (MACD)"]
    assert cell.bias is Bias.NEUTRAL
    assert cell.rule_ids == ["divergence"]


def test_divergence_row_states_when_there_is_none():
    highs = [Pivot(10, 100.0), Pivot(50, 105.0)]
    oscillator = [None] * 60
    oscillator[10], oscillator[50] = 60.0, 70.0
    cell = divergence_cell((("RSI", oscillator),), highs, [], 60, T)
    assert cell.labels == ["No divergence (RSI, MACD, Stochastic %K)"]


def divergence_fixture():
    """A top at index 20 (57.5, %K 94.6) and a higher top at index 40 (57.9, %K 94.4), with only two bars after it."""
    highs = [50.0] * 43  # flat bars never form a pivot, so only the two peaks are swings
    highs[20], highs[40] = 57.5, 57.9
    oscillator = [50.0] * 43
    oscillator[20], oscillator[40] = 94.6, 94.4
    return highs, [49.0] * 43, oscillator


def test_divergence_confirms_a_top_after_two_bars_not_five():
    highs, lows, _ = divergence_fixture()
    assert 40 not in [p.index for p in find_pivots(highs, lows, T.pivot_window, T.pivot_window)[0]]
    assert [p.index for p in divergence_pivots(highs, lows, T)[0]][-2:] == [20, 40]


def test_latest_higher_top_with_lower_stochastic_is_bearish_divergence():
    highs, lows, oscillator = divergence_fixture()
    div_highs, div_lows = divergence_pivots(highs, lows, T)
    cell = divergence_cell((("Stochastic %K", oscillator),), div_highs, div_lows, len(highs), T)
    assert cell.labels == ["Bearish divergence (Stochastic %K)"]


def test_divergence_row_is_unavailable_without_two_confirmed_swings():
    cell = divergence_cell((("RSI", [None] * 60),), [Pivot(10, 100.0)], [Pivot(12, 95.0)], 60, T)
    assert cell.bias is Bias.UNAVAILABLE
    assert cell.unavailable_reason == "Needs two confirmed swing highs or lows."


def test_volume_classifies_latest_candle_against_the_prior_average():
    cell = volume_cell(close_path([10] * 20, volume=100) + close_path([10], volume=250), T)
    assert cell.labels == ["Double average volume (high)", "2.50x the 20-candle average"]
    assert cell.values["volume_ratio"] == 2.5
    assert cell.bias is Bias.NEUTRAL


@pytest.mark.parametrize(
    ("latest", "label"),
    [(60, "Less than average volume"), (110, "Average volume"), (150, "More than average volume")],
)
def test_volume_bands(latest, label):
    cell = volume_cell(close_path([10] * 20, volume=100) + close_path([10], volume=latest), T)
    assert cell.labels[0] == label


def test_volume_is_unavailable_without_volume_or_enough_history():
    assert volume_cell(close_path([10] * 21), T).unavailable_reason == "Volume is not provided for this timeframe."
    assert "Needs about 21" in volume_cell(close_path([10] * 5, volume=100), T).unavailable_reason


def test_breakout_above_swing_high_on_the_latest_close_with_volume_confirmation():
    candles = close_path([100, 101, 102, 104, 106])
    labels = _breakout_labels(candles, [Pivot(2, 105.0)], [], volume_ratio=1.5, t=T)
    assert labels == ["Breakout above 105.00, volume confirms"]


def test_breakdown_below_swing_low_without_volume_confirmation():
    candles = close_path([110, 109, 108, 105, 103])
    labels = _breakout_labels(candles, [], [Pivot(2, 104.0)], volume_ratio=0.5, t=T)
    assert labels == ["Breakdown below 104.00, volume does not confirm"]


def test_no_breakout_when_the_level_was_not_crossed_by_the_latest_close():
    candles = close_path([100, 101, 102, 104, 106])
    assert _breakout_labels(candles, [Pivot(2, 150.0)], [], volume_ratio=None, t=T) == []


def test_fibonacci_pullback_of_latest_up_leg_names_nearest_level():
    candles = close_path([100, 112])
    labels = _fibonacci_labels(candles, [Pivot(5, 120.0)], [Pivot(2, 100.0)], T)
    assert labels == ["Fib 40.0% of up-leg pullback, near 38.2%"]


def test_fibonacci_bounce_of_latest_down_leg_without_nearby_level():
    candles = close_path([100, 104])
    labels = _fibonacci_labels(candles, [Pivot(2, 120.0)], [Pivot(5, 100.0)], T)
    assert labels == ["Fib 20.0% of down-leg bounce"]


def test_fibonacci_close_beyond_the_swing_leg_is_not_given_a_percentage():
    candles = close_path([100, 125])
    labels = _fibonacci_labels(candles, [Pivot(5, 120.0)], [Pivot(2, 100.0)], T)
    assert labels == ["Close outside the latest swing leg (no Fibonacci zone)"]


def test_fibonacci_needs_both_swings():
    assert _fibonacci_labels(close_path([100]), [], [Pivot(2, 100.0)], T) == []


def test_double_top_with_broken_neckline_is_bearish():
    candles = [bar(105, 105.5, 104.5, 105) for _ in range(40)]
    candles[15] = bar(101, 101.5, 100, 101)
    candles[-1] = bar(98, 98.5, 97.5, 98)
    cell = chart_pattern_cell(candles, [Pivot(10, 110.0), Pivot(25, 109.5)], [], T)
    assert cell.labels == ["Double Top, neckline 100.00 broken"]
    assert cell.bias is Bias.BEARISH


def test_double_top_candidate_while_neckline_holds():
    candles = [bar(105, 105.5, 104.5, 105) for _ in range(40)]
    candles[15] = bar(101, 101.5, 100, 101)
    cell = chart_pattern_cell(candles, [Pivot(10, 110.0), Pivot(25, 109.5)], [], T)
    assert cell.labels == ["Double Top candidate, neckline 100.00 holding"]
    assert cell.bias is Bias.NEUTRAL


def test_double_bottom_with_broken_neckline_is_bullish():
    candles = [bar(92, 95, 90, 92) for _ in range(40)]
    candles[15] = bar(93, 100, 91, 93)
    candles[-1] = bar(102, 102.5, 101.5, 102)
    cell = chart_pattern_cell(candles, [], [Pivot(10, 90.0), Pivot(25, 90.4)], T)
    assert cell.labels == ["Double Bottom, neckline 100.00 broken"]
    assert cell.bias is Bias.BULLISH


def test_no_double_pattern_is_labelled_neutral():
    candles = close_path([100 + i for i in range(40)])
    cell = chart_pattern_cell(candles, [Pivot(10, 110.0)], [Pivot(20, 90.0)], T)
    assert cell.labels == ["No double top / bottom"]
    assert cell.bias is Bias.NEUTRAL


def test_heikin_ashi_green_reports_the_single_wick_it_has():
    # PAPA Concept 3: a candle with no lower wick is decisive; the upper wick is reported.
    assert heikin_ashi_labels([bar(100, 110, 104, 108)]) == ["Heikin-Ashi green, upper wick"]


def test_heikin_ashi_green_with_wicks_on_both_sides_is_indecisive():
    assert heikin_ashi_labels([bar(100, 110, 95, 101)]) == ["Heikin-Ashi green, both wicks"]


def test_heikin_ashi_doji_with_both_wicks():
    assert heikin_ashi_labels([bar(100, 110, 90, 100)]) == ["Heikin-Ashi doji, both wicks"]


def test_heikin_ashi_red_in_a_falling_run_is_labelled():
    closes = [100, 98, 96, 94, 92, 90]
    candles = [bar(c + 2, c + 2, c - 0.5, c, i=i) for i, c in enumerate(closes)]
    label = heikin_ashi_labels(candles)[0]
    assert label.startswith("Heikin-Ashi red, ")
    assert label.endswith(("no wicks", "upper wick", "lower wick", "both wicks"))


def test_bollinger_three_sd_excursions_are_labelled():
    upper_beyond = bb_case([100, 101, 103, 107], [95] * 4, [99, 100, 102, 106], [104] * 4, [100] * 4, [96] * 4)
    lower_beyond = bb_case([100, 101, 103, 105], [95, 96, 94, 93], [99, 100, 102, 99], [104] * 4, [100] * 4, [96] * 4)
    inside = bb_case([100, 101, 103, 105], [95] * 4, [99, 100, 102, 104], [104] * 4, [100] * 4, [96] * 4)
    assert "Beyond +3 SD band" in upper_beyond.labels
    assert "Beyond -3 SD band" in lower_beyond.labels
    assert not {"Beyond +3 SD band", "Beyond -3 SD band"} & set(inside.labels)


def test_ema_long_stack_is_labelled_for_5_50_100_200():
    emas = {5: pad([120] * 4), 13: pad([115] * 4), 26: pad([112] * 4), 50: pad([110] * 4),
            100: pad([105] * 4), 150: pad([103] * 4), 200: pad([100] * 4)}
    cell = ema_cell(pad([121] * 4), emas, T)
    assert "POC, 5 > 50 > 100 and 50 > 200" in cell.labels
    assert cell.bias is Bias.BULLISH


def test_candle_patterns_bullish_harami_and_three_white_soldiers():
    harami = detect_candle_patterns([bar(110, 111, 99, 100), bar(102, 107.5, 101, 107)], False, False)
    assert "Bullish Harami" in harami.labels
    soldiers = detect_candle_patterns(
        [bar(100, 103.5, 99.5, 103), bar(102, 106.5, 101.5, 106), bar(105, 109.5, 104.5, 109)], False, False
    )
    assert "Three White Soldiers" in soldiers.labels
    assert soldiers.bias is Bias.BULLISH


def test_candle_pattern_three_black_crows():
    crows = detect_candle_patterns(
        [bar(110, 110.5, 106.5, 107), bar(108, 108.5, 103.5, 104), bar(105, 105.5, 100.5, 101)], False, False
    )
    assert "Three Black Crows" in crows.labels
    assert crows.bias is Bias.BEARISH


def test_checklist_rows_now_automate_volume_and_chart_patterns_without_new_rows():
    rows = {row.id: row for row in CHECKLIST_ROWS}
    assert rows["weapon_volume"].automated is True
    assert rows["chart_pattern"].automated is True
    assert len(CHECKLIST_ROWS) == 25


def test_section_two_rows_are_price_action_heikin_ashi_candlestick_significant_then_special_candles():
    row_ids = [row.id for row in CHECKLIST_ROWS if row.section == "2. Dow Theory Advanced + Price Action + Candlestick Pattern"]
    assert row_ids == ["price_action", "heikin_ashi", "candlestick_pattern", "significant_candle", "special_candles"]


def test_heikin_ashi_has_its_own_neutral_row_and_no_longer_sits_in_price_action():
    evaluation = evaluate_timeframe(make_candles(), T)
    heikin = evaluation.cells["heikin_ashi"]
    assert heikin.bias is Bias.NEUTRAL
    assert heikin.labels and all(label.startswith("Heikin-Ashi") for label in heikin.labels)
    assert not any("Heikin-Ashi" in label for label in evaluation.cells["price_action"].labels)


def test_candlestick_pattern_row_carries_the_pattern_bias_and_special_candles_is_location_only():
    evaluation = evaluate_timeframe(make_candles(), T)
    pattern = evaluation.cells["candlestick_pattern"]
    location = evaluation.cells["special_candles"]
    assert pattern.rule_ids == ["candles"]
    assert location.bias is Bias.NEUTRAL
    assert location.labels[0] in {"At / near support", "At / near resistance", "Not at support or resistance"}


def test_divergence_row_sits_directly_after_emas_in_the_indicators_section():
    row_ids = [row.id for row in CHECKLIST_ROWS]
    assert row_ids[row_ids.index("emas") + 1] == "divergence"
    assert {row.section for row in CHECKLIST_ROWS if row.id == "divergence"} == {"3. Check Indicators"}


# Bollinger side states and signal candle (live feed)


def test_upper_band_expanding_without_a_touch_is_labelled_by_side_not_ubbc():
    cell = bb_case([100, 101, 103, 104], [95] * 4, [99, 100, 102, 103], [100, 101, 103, 106], [100] * 4, [96] * 4)
    assert "UBBC, BB Expands" not in cell.labels
    assert "Upper band expanding" in cell.labels
    assert "Lower band flat" in cell.labels


def test_contracting_upper_band_that_was_touched_is_not_a_failure():
    cell = bb_case([100, 101, 103, 105], [95] * 4, [99, 100, 102, 104], [110, 108, 106, 104], [100] * 4, [96] * 4)
    assert "UBBC Failure, BKT" not in cell.labels
    assert "Upper band contracting" in cell.labels


def test_flat_upper_band_touched_within_recent_candles_is_a_failure():
    cell = bb_case([100, 101, 103, 105], [95] * 4, [99, 100, 102, 104], [104] * 4, [100] * 4, [96] * 4)
    assert "UBBC Failure, BKT" in cell.labels
    assert cell.bias is Bias.BEARISH


def _bb_forming(highs, lows, closes, upper, basis, lower):
    return bollinger_cell(pad(highs), pad(lows), pad(closes), pad(upper), pad(basis), pad(lower), T, forming=True)


def test_forming_latest_candle_does_not_decide_ubbc_but_the_closed_candle_does():
    highs, upper = [100, 101, 106, 104], [100, 101, 103, 106]
    closes, basis, lower = [99, 100, 104, 103], [100] * 4, [96] * 4
    closed_only = _bb_forming(highs, [95] * 4, closes, upper, basis, lower)
    assert "UBBC, BB Expands" in closed_only.labels
    assert "Forming candle touches UBB" not in closed_only.labels

    latest_decides = bb_case(highs, [95] * 4, closes, upper, basis, lower)
    assert "UBBC, BB Expands" not in latest_decides.labels


def test_forming_candle_touch_is_reported_as_a_note_not_a_signal():
    cell = _bb_forming([100, 101, 102, 107], [95] * 4, [99, 100, 101, 106], [104] * 4, [100] * 4, [96] * 4)
    assert "Forming candle touches UBB" in cell.labels
    assert "UBBC, BB Expands" not in cell.labels
    assert "UBBC Failure, BKT" not in cell.labels
