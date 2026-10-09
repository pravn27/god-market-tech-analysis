from datetime import datetime, timedelta, timezone

import pytest

from god_market_api.models import Bias, Candle
from god_market_api.mtf_checklist import (
    CHECKLIST_ROWS,
    ChecklistThresholds,
    adx_cell,
    bollinger_cell,
    dmi_cell,
    ema_cell,
    evaluate_timeframe,
    macd_cell,
    rsi_cell,
    stochastic_cell,
)

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
                              low=min(open_, close) - 0.5, close=close))
        price = close
    return candles


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
