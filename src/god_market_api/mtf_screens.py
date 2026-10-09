"""SMM Double / Triple Screen signals and decisions for the multi-timeframe checklist."""

from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from .models import (
    AnalysisTimeframe,
    LayerSignal,
    ScreenDecision,
    ScreenSignal,
    TimeframeScreen,
)
from .mtf_checklist import ChecklistThresholds, Series, TimeframeEvaluation, _at, _recent_cross

MACD = "MACD"
STOCHASTIC_RSI = "Stochastic / RSI"

DISCLAIMER = "Checklist signal derived from the SMM Double/Triple Screen rules — not financial advice."


@dataclass(frozen=True)
class LayerDefinition:
    name: str
    timeframes: Tuple[AnalysisTimeframe, AnalysisTimeframe]
    screen_indicator: str


SUPER_TIDE = "Super TIDE"
TIDE = "TIDE"
WAVE = "WAVE"
RIPPLE = "RIPPLE"

LAYERS: Tuple[LayerDefinition, ...] = (
    LayerDefinition(SUPER_TIDE, (AnalysisTimeframe.MONTHLY, AnalysisTimeframe.WEEKLY), MACD),
    LayerDefinition(TIDE, (AnalysisTimeframe.DAILY, AnalysisTimeframe.FOUR_HOUR), MACD),
    LayerDefinition(WAVE, (AnalysisTimeframe.FOUR_HOUR, AnalysisTimeframe.ONE_HOUR), STOCHASTIC_RSI),
    LayerDefinition(RIPPLE, (AnalysisTimeframe.ONE_HOUR, AnalysisTimeframe.FIFTEEN_MINUTE), MACD),
)

DOUBLE_SCREEN_PAIRS: Tuple[Tuple[str, str], ...] = ((TIDE, WAVE), (SUPER_TIDE, TIDE), (WAVE, RIPPLE))


def _unavailable(reason: str) -> TimeframeScreen:
    return TimeframeScreen(signal=ScreenSignal.UNAVAILABLE, unavailable_reason=reason)


def _state_label(fast: float, slow: float) -> Optional[str]:
    if fast > slow:
        return "PCO state"
    if fast < slow:
        return "NCO state"
    return None


def _last_move(series: Series) -> Optional[str]:
    """Direction of the most recent non-flat step before the latest candle."""
    for offset in range(1, len(series) - 1):
        now, before = _at(series, offset), _at(series, offset + 1)
        if now is None or before is None:
            return None
        if now > before:
            return "up"
        if now < before:
            return "down"
    return None


def macd_screen(line: Series, signal_line: Series) -> TimeframeScreen:
    """Tide/Ripple screen: BUY on an up tick or flat after a down move; SELL mirrors."""
    now, before, signal_now = _at(line), _at(line, 1), _at(signal_line)
    if now is None or before is None or signal_now is None:
        return _unavailable("MACD needs more candles.")
    if now > before:
        signal, labels = ScreenSignal.BUY, ["Up Tick"]
    elif now < before:
        signal, labels = ScreenSignal.SELL, ["Down Tick"]
    else:
        move = _last_move(line)
        if move == "down":
            signal, labels = ScreenSignal.BUY, ["Flat after Down"]
        elif move == "up":
            signal, labels = ScreenSignal.SELL, ["Flat after Up"]
        else:
            signal, labels = ScreenSignal.NOT_CLEAR, ["Flat"]
    state = _state_label(now, signal_now)
    if state:
        labels.append(state)
    return TimeframeScreen(signal=signal, labels=labels)


def wave_screen(k: Series, d: Series, rsi: Series, t: ChecklistThresholds) -> TimeframeScreen:
    """Wave screen: %K up tick or recent PCO with RSI not below 40 is BUY; SELL mirrors."""
    k_now, k_before, d_now, rsi_now = _at(k), _at(k, 1), _at(d), _at(rsi)
    if None in (k_now, k_before, d_now, rsi_now):
        return _unavailable("Stochastic / RSI need more candles.")
    cross = _recent_cross(k, d, t.recent_crossover_periods)
    up_tick, down_tick = k_now > k_before, k_now < k_before
    buy = (up_tick or (cross is not None and cross[0] == "up")) and rsi_now >= 40
    sell = (down_tick or (cross is not None and cross[0] == "down")) and rsi_now <= 60
    signal = ScreenSignal.BUY if buy and not sell else ScreenSignal.SELL if sell and not buy else ScreenSignal.NOT_CLEAR

    labels = ["Up Tick" if up_tick else "Down Tick" if down_tick else "Flat"]
    if cross:
        labels.append("Recent PCO" if cross[0] == "up" else "Recent NCO")
    state = _state_label(k_now, d_now)
    if state:
        labels.append(state)
    labels.append(f"RSI {rsi_now:.1f}")
    return TimeframeScreen(signal=signal, labels=labels)


def timeframe_screen(
    indicator: str, evaluation: Optional[TimeframeEvaluation], t: ChecklistThresholds
) -> TimeframeScreen:
    if evaluation is None:
        return _unavailable("Timeframe was not fetched.")
    if evaluation.series is None:
        return _unavailable(evaluation.unavailable_reason or "Timeframe is unavailable.")
    s = evaluation.series
    if indicator == MACD:
        return macd_screen(s.macd_line, s.macd_signal)
    return wave_screen(s.stoch_k, s.stoch_d, s.rsi, t)


def layer_signal(layer: LayerDefinition, screens: Sequence[TimeframeScreen]) -> LayerSignal:
    missing = [tf for tf, screen in zip(layer.timeframes, screens) if screen.signal is ScreenSignal.UNAVAILABLE]
    signals = {screen.signal for screen in screens}
    if missing:
        signal = ScreenSignal.UNAVAILABLE
    elif len(signals) == 1:
        signal = signals.pop()
    else:
        signal = ScreenSignal.NOT_CLEAR
    return LayerSignal(
        name=layer.name,
        timeframes=list(layer.timeframes),
        screen_indicator=layer.screen_indicator,
        signal=signal,
        screens=dict(zip(layer.timeframes, screens)),
        missing_timeframes=missing,
    )


def _incomplete(name: str, layers: Sequence[LayerSignal]) -> Optional[ScreenDecision]:
    missing: List[AnalysisTimeframe] = []
    for layer in layers:
        missing.extend(tf for tf in layer.missing_timeframes if tf not in missing)
    if not missing:
        return None
    return ScreenDecision(
        name=name,
        layers=[layer.name for layer in layers],
        decision=f"INCOMPLETE — {', '.join(tf.value for tf in missing)} unavailable",
        missing_timeframes=missing,
    )


def _not_clear(name: str, layers: Sequence[LayerSignal]) -> Optional[ScreenDecision]:
    if any(layer.signal is ScreenSignal.NOT_CLEAR for layer in layers):
        return ScreenDecision(name=name, layers=[layer.name for layer in layers], decision="NOT CLEAR")
    return None


def _side(signal: ScreenSignal) -> Tuple[str, str]:
    return ("Buy", "bullish") if signal is ScreenSignal.BUY else ("Sell", "bearish")


def double_screen(tide: LayerSignal, wave: LayerSignal) -> ScreenDecision:
    name = f"Double Screen ({tide.name} + {wave.name})"
    pending = _incomplete(name, (tide, wave)) or _not_clear(name, (tide, wave))
    if pending:
        return pending
    if tide.signal is wave.signal:
        decision = tide.signal.value
    else:
        decision = f"No {_side(tide.signal)[0]} — wait for {wave.name} to align with {tide.name}"
    return ScreenDecision(name=name, layers=[tide.name, wave.name], decision=decision)


def triple_screen(tide: LayerSignal, wave: LayerSignal, ripple: LayerSignal) -> ScreenDecision:
    """Entry decision plus the SMM position-management note for an open position in the Tide direction."""
    name = f"Triple Screen ({tide.name} + {wave.name} + {ripple.name})"
    layers = (tide, wave, ripple)
    pending = _incomplete(name, layers) or _not_clear(name, layers)
    if pending:
        return pending
    action, mood = _side(tide.signal)
    if tide.signal is wave.signal is ripple.signal:
        decision = f"{tide.signal.value} — go for refined entry"
        note = f"Stay {mood.capitalize()}"
    elif tide.signal is not wave.signal:
        decision = f"No {action} — wait for {wave.name} to align with {tide.name}"
        note = f"Exit in {wave.name} / refined exit in {ripple.name}" if wave.signal is ripple.signal else None
    else:
        decision = f"No {action} — wait for {ripple.name} to align with {tide.name} / {wave.name}"
        note = f"Carefully {mood} — keep an eye on {wave.name}"
    return ScreenDecision(name=name, layers=[layer.name for layer in layers], decision=decision, position_note=note)


@dataclass(frozen=True)
class ScreenResult:
    layers: List[LayerSignal]
    double_screens: List[ScreenDecision]
    triple_screen: ScreenDecision


def evaluate_screens(
    evaluations: Mapping[AnalysisTimeframe, Optional[TimeframeEvaluation]], t: ChecklistThresholds
) -> ScreenResult:
    layers = [
        layer_signal(layer, [timeframe_screen(layer.screen_indicator, evaluations.get(tf), t) for tf in layer.timeframes])
        for layer in LAYERS
    ]
    by_name = {layer.name: layer for layer in layers}
    return ScreenResult(
        layers=layers,
        double_screens=[double_screen(by_name[a], by_name[b]) for a, b in DOUBLE_SCREEN_PAIRS],
        triple_screen=triple_screen(by_name[TIDE], by_name[WAVE], by_name[RIPPLE]),
    )
