"""HTTP and use-case tests for the fixture-backed Global Market slice."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.global_market import FixtureGlobalMarketSnapshotProvider, GlobalMarketSnapshotService
from god_market_api.models import (
    DataSource,
    GlobalMarketCompleteness,
    GlobalMarketGroup,
    GlobalMarketInstrument,
    GlobalMarketSnapshot,
    MarketDirection,
    SourceState,
)


NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


def instrument(symbol: str, direction: MarketDirection) -> GlobalMarketInstrument:
    if direction is MarketDirection.UNAVAILABLE:
        return GlobalMarketInstrument(
            symbol=symbol,
            display_name=symbol,
            direction=direction,
            source=DataSource.FIXTURE,
            freshness_state=SourceState.UNAVAILABLE,
            unavailable_reason="Fixture does not include a current value for this item.",
        )
    return GlobalMarketInstrument(
        symbol=symbol,
        display_name=symbol,
        last_price=100.0,
        change_percent=0.5,
        direction=direction,
        source=DataSource.FIXTURE,
        source_timestamp=NOW,
        freshness_state=SourceState.READY,
    )


def test_snapshot_service_preserves_groups_and_excludes_unavailable_from_directional_breadth() -> None:
    service = GlobalMarketSnapshotService(clock=lambda: NOW)

    snapshot = service.build_snapshot(
        timeframe="daily",
        groups=[
            GlobalMarketGroup(
                name="USA",
                instruments=[
                    instrument("TVC:SPX", MarketDirection.ADVANCING),
                    instrument("TVC:VIX", MarketDirection.UNAVAILABLE),
                ],
            ),
            GlobalMarketGroup(
                name="INDIA ADRS",
                instruments=[instrument("NYSE:INFY", MarketDirection.DECLINING)],
            ),
        ],
    )

    assert [group.name for group in snapshot.groups] == ["USA", "INDIA ADRS"]
    assert snapshot.completeness is GlobalMarketCompleteness.PARTIAL
    assert snapshot.breadth.model_dump() == {
        "advancing": 1,
        "declining": 1,
        "unchanged": 0,
        "unavailable": 1,
    }
    assert "excluded from advancing, declining, and unchanged breadth counts" in snapshot.warnings[0]


class UnavailableSnapshotProvider:
    async def get_snapshot(self, timeframe: str) -> GlobalMarketSnapshot:
        return GlobalMarketSnapshotService(clock=lambda: NOW).build_snapshot(
            timeframe=timeframe,
            groups=[
                GlobalMarketGroup(
                    name="USA",
                    instruments=[instrument("TVC:SPX", MarketDirection.UNAVAILABLE)],
                )
            ],
        )


def test_global_market_endpoint_returns_ordered_fixture_evidence() -> None:
    client = TestClient(create_app(global_market_provider=FixtureGlobalMarketSnapshotProvider()))

    response = client.get("/api/v1/global-market-sentiment", params={"timeframe": "daily"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["watchlist_name"] == "PS_Global_Indices"
    assert [group["name"] for group in payload["groups"]] == [
        "USA",
        "EUROPE",
        "ASIA PACIFIC",
        "INDIA ADRS",
    ]
    assert payload["completeness"] == "partial"
    assert payload["breadth"]["unavailable"] == 1
    assert any("Fixture data only" in warning for warning in payload["warnings"])


def test_global_market_endpoint_keeps_unavailable_state_explicit() -> None:
    client = TestClient(create_app(global_market_provider=UnavailableSnapshotProvider()))

    response = client.get("/api/v1/global-market-sentiment")

    assert response.status_code == 200
    payload = response.json()
    assert payload["completeness"] == "unavailable"
    assert payload["breadth"] == {"advancing": 0, "declining": 0, "unchanged": 0, "unavailable": 1}
