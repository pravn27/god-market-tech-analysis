from datetime import datetime, timedelta, timezone

from god_market_api.models import Bias, Candle
from god_market_api.price_structure import Pivot
from god_market_api.significant_candles import (
    NO_EVENT_LABEL,
    find_significant_candles,
    significant_candle_evidence,
)

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def candle(open_, high, low, close, i=0):
    return Candle(timestamp=START + timedelta(hours=i), open=open_, high=high, low=low, close=close, volume=100.0)


def evaluate(candles, pivot_highs=(), pivot_lows=(), window=1, **overrides):
    kwargs = dict(
        at_support=False,
        at_resistance=False,
        pattern_labels=[],
        action_labels={},
        bollinger_labels=[],
        rsi_now=None,
        rsi_prev=None,
        volume_ratio=None,
        volume_threshold=2.0,
    )
    kwargs.update(overrides)
    return significant_candle_evidence(candles, list(pivot_highs), list(pivot_lows), window, **kwargs)


def test_close_beyond_previous_high_is_a_significant_bullish_candle():
    candles = [candle(100, 101, 99, 100, 0), candle(100, 103, 99, 102, 1), candle(101, 102, 100, 101, 2)]
    found = find_significant_candles(candles, [], [], 1)
    assert len(found) == 1
    assert found[0].index == 1 and found[0].direction == 1
    assert (found[0].high, found[0].low) == (103, 99)


def test_bullish_candle_takes_out_and_breaks_out_the_significant_high():
    candles = [candle(100, 101, 99, 100, 0), candle(100, 103, 99, 102, 1), candle(101, 104, 100, 104, 2)]
    result, values = evaluate(candles)
    assert "Takes out high of significant candle 103.00 (1 candles ago)" in result.labels
    assert "BO of significant candle 103.00 (1 candles ago)" in result.labels
    assert result.label_biases["BO of significant candle 103.00 (1 candles ago)"] is Bias.BULLISH
    assert result.bias is Bias.BULLISH
    assert values["stop_reference_low"] == 99 and values["stop_reference_high"] == 103


def test_bearish_candle_takes_out_and_breaks_down_the_significant_low():
    candles = [candle(100, 101, 99, 100, 0), candle(100, 101, 97, 98, 1), candle(98, 99, 95, 96, 2)]
    result, values = evaluate(candles)
    assert "Takes out low of significant candle 97.00 (1 candles ago)" in result.labels
    assert "BD of significant candle 97.00 (1 candles ago)" in result.labels
    assert result.label_biases["BD of significant candle 97.00 (1 candles ago)"] is Bias.BEARISH
    assert result.bias is Bias.BEARISH
    assert values["stop_reference_high"] == 101


def test_gap_up_filled_by_the_latest_candle_is_an_exhaustion_gap_fill():
    candles = [
        candle(100, 101, 99, 100, 0),
        candle(106, 108, 105, 107, 1),  # gap up from 101 to 105, and a bullish significant candle
        candle(103, 104, 100, 102, 2),  # reaches back down to 101
    ]
    result, _ = evaluate(candles)
    assert "Fills exhaustion gap up 101.00-105.00" in result.labels
    assert result.label_biases["Fills exhaustion gap up 101.00-105.00"] is Bias.NEUTRAL


def test_breakout_of_a_confirmed_swing_high_is_reported_as_resistance_break():
    candles = [
        candle(100, 105, 99, 104, 0),  # swing high 105 at index 0
        candle(104, 104, 101, 102, 1),
        candle(102, 103, 101, 103, 2),
        candle(103, 107, 102, 106, 3),  # closes through 105
    ]
    result, _ = evaluate(candles, pivot_highs=[Pivot(index=0, price=105.0)], window=1)
    assert "Breaks out resistance 105.00" in result.labels
    assert result.label_biases["Breaks out resistance 105.00"] is Bias.BULLISH


def test_rsi_brought_above_40_is_bullish():
    candles = [candle(100, 101, 99, 100, 0), candle(100, 100.5, 99.5, 100, 1), candle(100, 100.8, 99.2, 100.2, 2)]
    result, _ = evaluate(candles, rsi_now=42.0, rsi_prev=39.0)
    assert "RSI brought above 40" in result.labels
    assert result.label_biases["RSI brought above 40"] is Bias.BULLISH


def test_bb_failure_labels_map_to_bkt_and_bkp_candles():
    candles = [candle(100, 101, 99, 100, 0), candle(100, 100.5, 99.5, 100, 1), candle(100, 100.8, 99.2, 100.2, 2)]
    result, _ = evaluate(candles, bollinger_labels=["UBBC Failure, BKT"])
    assert result.label_biases["BKT candle (upper band failure)"] is Bias.BEARISH


def test_no_event_is_neutral_with_no_stop_reference():
    candles = [candle(100, 101, 99, 100, 0), candle(100, 100.5, 99.5, 100, 1), candle(100, 100.8, 99.2, 100.2, 2)]
    result, values = evaluate(candles)
    assert result.labels == [NO_EVENT_LABEL]
    assert result.bias is Bias.NEUTRAL
    assert values == {}
