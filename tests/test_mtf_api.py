"""HTTP contract tests for the local multi-timeframe endpoint."""

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.models import ChartContext, DataSource, SourceHealth, SourceState
from god_market_api.providers import DataSourceUnavailableError


class MtfFixtureProvider:
    def __init__(self, unavailable: bool = False) -> None:
        self.unavailable = unavailable
        self.calls: list[str] = []

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source=DataSource.OFFICIAL_MCP,
            state=SourceState.READY,
            detail="Test provider is ready.",
            checked_at=datetime.now(timezone.utc),
        )

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        self.calls.append(timeframe)
        if self.unavailable:
            raise DataSourceUnavailableError("Source is unavailable for this timeframe.")
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=datetime.now(timezone.utc),
            freshness_state=SourceState.READY,
        )


def test_mtf_endpoint_returns_the_documented_typed_response() -> None:
    provider = MtfFixtureProvider()
    client = TestClient(create_app(provider=provider))

    response = client.get("/api/v1/multi-timeframe-context/NSE:NIFTY")

    assert response.status_code == 200
    payload = response.json()
    assert payload["completeness"] == "complete"
    assert set(payload["contexts"]) == {"monthly", "weekly", "daily", "4h", "1h", "15m"}
    assert [layer["name"] for layer in payload["layers"]] == [
        "Super TIDE",
        "TIDE",
        "WAVE",
        "Ripple / Super Ripple",
    ]


def test_mtf_endpoint_rejects_an_invalid_timeframe_selection() -> None:
    client = TestClient(create_app(provider=MtfFixtureProvider()))

    response = client.get("/api/v1/multi-timeframe-context/NSE:NIFTY", params={"timeframe": "2h"})

    assert response.status_code == 422
    assert "timeframe" in response.text


def test_mtf_endpoint_returns_safe_503_with_typed_unavailable_context() -> None:
    client = TestClient(create_app(provider=MtfFixtureProvider(unavailable=True)))

    response = client.get("/api/v1/multi-timeframe-context/NSE:NIFTY")

    assert response.status_code == 503
    assert response.json()["detail"]["result"]["completeness"] == "unavailable"
    assert "No usable market context" in response.json()["detail"]["message"]
