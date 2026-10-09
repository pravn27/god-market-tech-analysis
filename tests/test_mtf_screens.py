import pytest

from god_market_api.models import AnalysisTimeframe as TF, LayerSignal, ScreenSignal, TimeframeScreen
from god_market_api.mtf_checklist import ChecklistThresholds, evaluate_timeframe
from god_market_api.mtf_screens import (
    LAYERS,
    double_screen,
    evaluate_screens,
    layer_signal,
    macd_screen,
    triple_screen,
    wave_screen,
)

from test_mtf_checklist import make_candles, pad

T = ChecklistThresholds()
BUY, SELL, NOT_CLEAR, UNAVAILABLE = (
    ScreenSignal.BUY,
    ScreenSignal.SELL,
    ScreenSignal.NOT_CLEAR,
    ScreenSignal.UNAVAILABLE,
)


def layer(name, signal, missing=()):
    return LayerSignal(name=name, timeframes=[], screen_indicator="MACD", signal=signal, missing_timeframes=list(missing))


# Per-timeframe screens


def test_macd_up_tick_is_buy_with_state():
    screen = macd_screen(pad([1, 2, 3]), pad([0, 0, 0]))
    assert screen.signal is BUY
    assert screen.labels == ["Up Tick", "PCO state"]


def test_macd_down_tick_is_sell():
    screen = macd_screen(pad([3, 2, 1]), pad([2, 2, 2]))
    assert screen.signal is SELL
    assert screen.labels == ["Down Tick", "NCO state"]


def test_macd_flat_after_down_is_buy_and_flat_after_up_is_sell():
    assert macd_screen(pad([5, 4, 3, 3]), pad([4] * 4)).labels[0] == "Flat after Down"
    assert macd_screen(pad([5, 4, 3, 3]), pad([4] * 4)).signal is BUY
    assert macd_screen(pad([1, 2, 3, 3]), pad([2] * 4)).signal is SELL


def test_macd_unavailable_without_history():
    assert macd_screen([None, None], [None, None]).signal is UNAVAILABLE


def test_wave_buy_on_k_up_tick_with_rsi_not_bearish():
    screen = wave_screen(pad([40, 45, 50]), pad([50, 49, 48]), pad([52] * 3), T)
    assert screen.signal is BUY
    assert "Up Tick" in screen.labels and "PCO state" in screen.labels


def test_wave_buy_blocked_when_rsi_below_40():
    assert wave_screen(pad([40, 45, 50]), pad([50, 49, 48]), pad([35] * 3), T).signal is NOT_CLEAR


def test_wave_sell_on_k_down_tick_with_rsi_not_bullish():
    assert wave_screen(pad([60, 55, 50]), pad([50, 52, 54]), pad([48] * 3), T).signal is SELL


def test_wave_conflicting_tick_and_recent_cross_is_not_clear():
    # %K crossed above %D recently (buy evidence) but the latest tick is down (sell evidence).
    screen = wave_screen(pad([40, 52, 51]), pad([45, 46, 47]), pad([50] * 3), T)
    assert screen.signal is NOT_CLEAR
    assert "Recent PCO" in screen.labels


# Layers


def test_layer_agreement_and_disagreement():
    tide = LAYERS[1]
    buy, sell = TimeframeScreen(signal=BUY), TimeframeScreen(signal=SELL)
    assert layer_signal(tide, [buy, buy]).signal is BUY
    assert layer_signal(tide, [buy, sell]).signal is NOT_CLEAR


def test_layer_with_missing_timeframe_is_unavailable_and_names_it():
    result = layer_signal(LAYERS[1], [TimeframeScreen(signal=BUY), TimeframeScreen(signal=UNAVAILABLE)])
    assert result.signal is UNAVAILABLE
    assert result.missing_timeframes == [TF.FOUR_HOUR]


# Double Screen


@pytest.mark.parametrize(
    "tide, wave, decision",
    [
        (BUY, BUY, "BUY"),
        (BUY, SELL, "No Buy — wait for WAVE to align with TIDE"),
        (SELL, SELL, "SELL"),
        (SELL, BUY, "No Sell — wait for WAVE to align with TIDE"),
        (NOT_CLEAR, BUY, "NOT CLEAR"),
        (SELL, NOT_CLEAR, "NOT CLEAR"),
    ],
)
def test_double_screen_table(tide, wave, decision):
    assert double_screen(layer("TIDE", tide), layer("WAVE", wave)).decision == decision


def test_double_screen_incomplete_names_missing_timeframe():
    result = double_screen(layer("TIDE", BUY), layer("WAVE", UNAVAILABLE, [TF.ONE_HOUR]))
    assert result.decision == "INCOMPLETE — 1h unavailable"
    assert result.missing_timeframes == [TF.ONE_HOUR]


# Triple Screen


@pytest.mark.parametrize(
    "tide, wave, ripple, decision, note",
    [
        (BUY, BUY, BUY, "BUY — go for refined entry", "Stay Bullish"),
        (BUY, SELL, BUY, "No Buy — wait for WAVE to align with TIDE", None),
        (SELL, SELL, BUY, "No Sell — wait for RIPPLE to align with TIDE / WAVE", "Carefully bearish — keep an eye on WAVE"),
        (BUY, BUY, SELL, "No Buy — wait for RIPPLE to align with TIDE / WAVE", "Carefully bullish — keep an eye on WAVE"),
        (BUY, SELL, SELL, "No Buy — wait for WAVE to align with TIDE", "Exit in WAVE / refined exit in RIPPLE"),
        (SELL, SELL, SELL, "SELL — go for refined entry", "Stay Bearish"),
        (SELL, BUY, SELL, "No Sell — wait for WAVE to align with TIDE", None),
        (SELL, BUY, BUY, "No Sell — wait for WAVE to align with TIDE", "Exit in WAVE / refined exit in RIPPLE"),
        (BUY, BUY, NOT_CLEAR, "NOT CLEAR", None),
    ],
)
def test_triple_screen_table(tide, wave, ripple, decision, note):
    result = triple_screen(layer("TIDE", tide), layer("WAVE", wave), layer("RIPPLE", ripple))
    assert result.decision == decision
    assert result.position_note == note


def test_triple_screen_incomplete():
    result = triple_screen(
        layer("TIDE", UNAVAILABLE, [TF.DAILY]), layer("WAVE", BUY), layer("RIPPLE", UNAVAILABLE, [TF.FIFTEEN_MINUTE])
    )
    assert result.decision == "INCOMPLETE — daily, 15m unavailable"


# End to end


def test_evaluate_screens_reuses_shared_timeframes_and_flags_missing():
    full = evaluate_timeframe(make_candles(), T)
    evaluations = {tf: full for tf in TF}
    evaluations[TF.MONTHLY] = None
    result = evaluate_screens(evaluations, T)

    assert [layer.name for layer in result.layers] == ["Super TIDE", "TIDE", "WAVE", "RIPPLE"]
    assert result.layers[0].signal is UNAVAILABLE
    tide_4h = result.layers[1].screens[TF.FOUR_HOUR]
    wave_4h = result.layers[2].screens[TF.FOUR_HOUR]
    assert not any(label.startswith("RSI") for label in tide_4h.labels)
    assert any(label.startswith("RSI") for label in wave_4h.labels)
    assert [d.name for d in result.double_screens] == [
        "Double Screen (TIDE + WAVE)",
        "Double Screen (Super TIDE + TIDE)",
        "Double Screen (WAVE + RIPPLE)",
    ]
    assert result.double_screens[1].decision == "INCOMPLETE — monthly unavailable"
    assert not result.triple_screen.decision.startswith("INCOMPLETE")
