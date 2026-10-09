import math
from datetime import datetime, timedelta, timezone

import pytest

from god_market_api.models import Candle
from god_market_api.technical_indicators import (
    IndicatorProfile,
    InvalidCandlesError,
    atr,
    bollinger_bands,
    calculate_indicators,
    candle_issue,
    dmi,
    ema,
    macd,
    rma,
    rsi,
    sma,
    stochastic,
)


def approx_list(values, expected, tol=1e-9):
    assert len(values) == len(expected)
    for actual, wanted in zip(values, expected):
        if wanted is None:
            assert actual is None
        else:
            assert actual == pytest.approx(wanted, abs=tol)


def candles_from(rows):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(timestamp=start + timedelta(days=i), open=o, high=h, low=l, close=c, volume=None)
        for i, (o, h, l, c) in enumerate(rows)
    ]


def test_sma_needs_full_window():
    approx_list(sma([1, 2, 3, 4, 5], 3), [None, None, 2, 3, 4])


def test_sma_propagates_missing_inputs():
    approx_list(sma([None, 2, 4, 6], 2), [None, None, 3, 5])


def test_ema_is_seeded_with_sma_like_tradingview():
    # alpha = 0.5; seed = mean(1, 2, 3) = 2; then 0.5 * x + 0.5 * prev
    approx_list(ema([1, 2, 3, 4, 5, 6], 3), [None, None, 2, 3, 4, 5])


def test_ema_starts_after_leading_missing_values():
    approx_list(ema([None, None, 2, 4, 6, 8], 2), [None, None, None, 3, 5, 7])


def test_rma_uses_wilder_smoothing():
    # alpha = 1/3; seed = mean(3, 6, 9) = 6; next = (12 + 2 * 6) / 3 = 8
    approx_list(rma([3, 6, 9, 12], 3), [None, None, 6, 8])


def test_rsi_is_100_for_only_gains_and_0_for_only_losses():
    rising = rsi([float(i) for i in range(1, 21)], 14)
    falling = rsi([float(i) for i in range(20, 0, -1)], 14)
    assert rising[:14] == [None] * 14
    assert rising[-1] == pytest.approx(100.0)
    assert falling[-1] == pytest.approx(0.0)


def test_rsi_hand_checked_value():
    # changes: +1, -1, +2 -> period 2 Wilder:
    # bar2 seed: up=mean(1,0)=0.5, down=mean(0,1)=0.5 -> 50
    # bar3: up=(2 + 0.5)/2=1.25, down=(0 + 0.5)/2=0.25 -> 100 - 100/(1+5) = 83.333...
    approx_list(rsi([10, 11, 10, 12], 2), [None, None, 50.0, 100 - 100 / 6])


def test_macd_of_constant_series_is_zero():
    line, signal, hist = macd([100.0] * 40, 12, 26, 9)
    assert line[24] is None and line[25] == pytest.approx(0.0)
    assert signal[32] is None and signal[33] == pytest.approx(0.0)
    assert hist[-1] == pytest.approx(0.0)


def test_macd_matches_ema_difference():
    closes = [float(x) for x in [10, 11, 13, 12, 15, 16, 18, 17, 19, 21, 22, 20]]
    line, signal, hist = macd(closes, 2, 4, 3)
    fast, slow = ema(closes, 2), ema(closes, 4)
    for i, value in enumerate(line):
        if slow[i] is None:
            assert value is None
        else:
            assert value == pytest.approx(fast[i] - slow[i])
    expected_signal = ema(line, 3)
    approx_list(signal, expected_signal)
    for i, value in enumerate(hist):
        if signal[i] is None:
            assert value is None
        else:
            assert value == pytest.approx(line[i] - signal[i])


def test_bollinger_uses_population_standard_deviation():
    upper, basis, lower = bollinger_bands([2, 4, 4, 4, 5, 5, 7, 9], 8, 2.0)
    # mean 5, population stdev 2
    assert basis[-1] == pytest.approx(5.0)
    assert upper[-1] == pytest.approx(9.0)
    assert lower[-1] == pytest.approx(1.0)
    assert upper[-2] is None


def test_stochastic_hand_checked_with_smoothing():
    highs = [10, 11, 12, 13, 14, 15]
    lows = [8, 9, 10, 11, 12, 13]
    closes = [9, 10, 11, 13, 12, 15]
    k, d = stochastic(highs, lows, closes, 3, 1, 2)
    # raw %K at i=2: (11-8)/(12-8)=75; i=3: (13-9)/(13-9)=100; i=4: (12-10)/(14-10)=50; i=5: (15-11)/(15-11)=100
    approx_list(k, [None, None, 75.0, 100.0, 50.0, 100.0])
    approx_list(d, [None, None, None, 87.5, 75.0, 75.0])


def test_stochastic_zero_range_is_unavailable():
    k, d = stochastic([5, 5, 5], [5, 5, 5], [5, 5, 5], 3, 1, 1)
    assert k == [None, None, None]
    assert d == [None, None, None]


def test_atr_uses_previous_close_for_true_range():
    highs = [10, 12, 11]
    lows = [8, 9, 7]
    closes = [9, 11, 8]
    # TR: 2 (first bar high-low), max(3, |12-9|, |9-9|)=3, max(4, |11-11|, |7-11|)=4
    approx_list(atr(highs, lows, closes, 2), [None, 2.5, (4 + 2.5) / 2])


def test_dmi_for_steady_uptrend_has_no_negative_movement():
    n = 60
    highs = [100 + 2 * i for i in range(n)]
    lows = [h - 3 for h in highs]
    closes = [h - 1 for h in highs]
    plus_di, minus_di, adx = dmi(highs, lows, closes, 14, 14)
    assert plus_di[13] is None and plus_di[14] is not None
    assert minus_di[-1] == pytest.approx(0.0)
    # +DM = 2 every bar, TR = max(3, |h - prev_close|=3, ...) = 3 -> +DI = 66.67
    assert plus_di[-1] == pytest.approx(200 / 3)
    assert adx[-1] == pytest.approx(100.0)
    assert adx[26] is None and adx[27] is not None


def test_candle_issue_detects_bad_input():
    good = candles_from([(1, 2, 0.5, 1.5), (1.5, 2.5, 1, 2)])
    assert candle_issue(good) is None
    assert candle_issue([]) == "No candles were returned."
    bad = candles_from([(1, 2, 0.5, float("nan"))])
    assert "non-finite" in candle_issue(bad)
    reversed_rows = list(reversed(good))
    assert "ascending" in candle_issue(reversed_rows)
    inverted = candles_from([(1, 0.5, 2, 1.5)])
    assert "high below low" in candle_issue(inverted)


def test_calculate_indicators_reports_lengths_and_profile():
    rows = [(100 + i, 102 + i, 99 + i, 101 + i) for i in range(60)]
    result = calculate_indicators(candles_from(rows), IndicatorProfile())
    assert result.profile.version == "mtf-checklist-v1"
    assert len(result.closes) == 60
    assert result.ema[5][-1] is not None
    assert result.ema[200][-1] is None
    assert result.rsi[-1] == pytest.approx(100.0)
    assert set(result.ema) == {5, 13, 26, 50, 100, 150, 200}
    for series in (result.macd_line, result.bb_basis, result.adx, result.stoch_k, result.atr):
        assert len(series) == 60
        assert series[-1] is not None and math.isfinite(series[-1])


def test_calculate_indicators_rejects_invalid_candles():
    with pytest.raises(InvalidCandlesError):
        calculate_indicators([], IndicatorProfile())
