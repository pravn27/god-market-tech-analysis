"""Contract tests for Global Market Sentiment source evidence."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from god_market_api.models import (
    DataSource,
    GlobalMarketBreadth,
    GlobalMarketCompleteness,
    GlobalMarketGroup,
    GlobalMarketInstrument,
    GlobalMarketSnapshot,
    MarketDirection,
    SourceState,
)


NOW = datetime(2026, 10, 6, 11, 30, tzinfo=timezone.utc)


def available_instrument(symbol: str, direction: MarketDirection) -> GlobalMarketInstrument:
    return GlobalMarketInstrument(
        symbol=symbol,
        display_name=symbol,
        last_price=100.0,
        change_percent=0.5 if direction is MarketDirection.ADVANCING else -0.5,
        direction=direction,
        source=DataSource.OFFICIAL_MCP,
        source_timestamp=NOW,
        freshness_state=SourceState.READY,
    )


def test_global_market_snapshot_preserves_group_order_and_source_evidence() -> None:
    usa = GlobalMarketGroup(
        name="USA",
        instruments=[available_instrument("TVC:SPX", MarketDirection.ADVANCING)],
    )
    europe = GlobalMarketGroup(name="EUROPE", instruments=[])
    snapshot = GlobalMarketSnapshot(
        watchlist_name="PS_Global_Indices",
        read_at=NOW,
        timeframe="daily",
        completeness=GlobalMarketCompleteness.PARTIAL,
        groups=[usa, europe],
        breadth=GlobalMarketBreadth(advancing=1, declining=0, unchanged=0, unavailable=0),
    )

    assert [group.name for group in snapshot.groups] == ["USA", "EUROPE"]
    assert snapshot.groups[0].instruments[0].source is DataSource.OFFICIAL_MCP
    assert snapshot.groups[0].instruments[0].source_timestamp == NOW


def test_fixture_can_represent_unavailable_instrument_without_neutralizing_it() -> None:
    unavailable = GlobalMarketInstrument(
        symbol="TVC:VIX",
        display_name="Volatility S&P 500 Index",
        direction=MarketDirection.UNAVAILABLE,
        source=DataSource.DESKTOP_BRIDGE,
        freshness_state=SourceState.UNAVAILABLE,
        unavailable_reason="No current source context is available.",
    )

    assert unavailable.last_price is None
    assert unavailable.change_percent is None
    assert unavailable.direction is MarketDirection.UNAVAILABLE


def test_unavailable_direction_requires_a_reason() -> None:
    with pytest.raises(ValidationError, match="unavailable_reason"):
        GlobalMarketInstrument(
            symbol="TVC:VIX",
            display_name="Volatility S&P 500 Index",
            direction=MarketDirection.UNAVAILABLE,
            source=DataSource.DESKTOP_BRIDGE,
            freshness_state=SourceState.UNAVAILABLE,
        )


def test_global_market_breadth_rejects_negative_counts() -> None:
    with pytest.raises(ValidationError):
        GlobalMarketBreadth(advancing=-1, declining=0, unchanged=0, unavailable=0)
