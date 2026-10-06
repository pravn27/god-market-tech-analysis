from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from god_market_api.models import (
    AnalysisTimeframe,
    ChartContext,
    DataSource,
    MultiTimeframeCompleteness,
    SourceState,
    TimeframeContextResult,
    default_mtf_layers,
    default_mtf_timeframes,
)


def test_default_mtf_policy_contains_each_requested_timeframe_once():
    assert default_mtf_timeframes() == (
        AnalysisTimeframe.MONTHLY,
        AnalysisTimeframe.WEEKLY,
        AnalysisTimeframe.DAILY,
        AnalysisTimeframe.FOUR_HOUR,
        AnalysisTimeframe.ONE_HOUR,
        AnalysisTimeframe.FIFTEEN_MINUTE,
    )


def test_default_mtf_layers_share_4h_and_1h_without_duplicate_context_requests():
    layers = default_mtf_layers()

    assert [layer.name for layer in layers] == ["Super TIDE", "TIDE", "WAVE", "Ripple / Super Ripple"]
    assert layers[1].timeframes == (AnalysisTimeframe.DAILY, AnalysisTimeframe.FOUR_HOUR)
    assert layers[2].timeframes == (AnalysisTimeframe.FOUR_HOUR, AnalysisTimeframe.ONE_HOUR)
    assert layers[3].timeframes == (AnalysisTimeframe.ONE_HOUR, AnalysisTimeframe.FIFTEEN_MINUTE)


def test_timeframe_context_result_requires_exactly_one_of_context_or_unavailable_reason():
    context = ChartContext(
        symbol="NSE:NIFTY",
        timeframe="1D",
        source=DataSource.OFFICIAL_MCP,
        source_timestamp=datetime.now(timezone.utc),
        freshness_state=SourceState.READY,
    )

    result = TimeframeContextResult(timeframe=AnalysisTimeframe.DAILY, context=context)

    assert result.context == context
    assert result.unavailable_reason is None

    with pytest.raises(ValidationError):
        TimeframeContextResult(timeframe=AnalysisTimeframe.DAILY)

    with pytest.raises(ValidationError):
        TimeframeContextResult(
            timeframe=AnalysisTimeframe.DAILY,
            context=context,
            unavailable_reason="Rate limited",
        )


def test_completeness_contract_has_complete_partial_and_unavailable_states():
    assert {state.value for state in MultiTimeframeCompleteness} == {"complete", "partial", "unavailable"}
