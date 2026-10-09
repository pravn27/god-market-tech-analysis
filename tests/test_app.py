from datetime import datetime, timezone

from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.desktop_bridge import TradingViewDesktopWatchlistReader
from god_market_api.models import ChartContext, DataSource, SourceHealth, SourceState
from god_market_api.providers import OfficialMCPProvider


class ReadyProvider:
    async def health(self):
        return SourceHealth(
            source=DataSource.OFFICIAL_MCP,
            state=SourceState.READY,
            detail="Test provider is ready.",
            checked_at=datetime.now(timezone.utc),
        )

    async def get_chart_context(self, symbol, timeframe):
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=datetime.now(timezone.utc),
            freshness_state=SourceState.READY,
        )


class ReadyOAuth:
    async def status(self):
        return type("State", (), {"status": "authenticated", "completed_at": None, "tools": ["get_ohlcv"], "error": None})()

    async def start(self):
        return type("State", (), {"status": "awaiting_user", "authorization_url": "https://example.test/authorize", "error": None})()

    async def complete_callback(self, code, state):
        return type("State", (), {"status": "exchanging_token"})()


def test_health_reports_source_state():
    client = TestClient(
        create_app(ReadyProvider(), desktop_watchlist_reader=TradingViewDesktopWatchlistReader(None))
    )

    response = client.get("/health")

    assert response.status_code == 200
    official, desktop = response.json()["sources"]
    assert official["source"] == "official_mcp"
    assert official["state"] == "ready"
    assert desktop["source"] == "desktop_bridge"
    assert desktop["state"] == "not_configured"


def test_chart_context_preserves_source_and_timeframe():
    client = TestClient(create_app(ReadyProvider()))

    response = client.get("/api/v1/chart-context/NSE:NIFTY", params={"timeframe": "1h"})

    assert response.status_code == 200
    assert response.json()["symbol"] == "NSE:NIFTY"
    assert response.json()["timeframe"] == "1h"
    assert response.json()["source"] == "official_mcp"


def test_unconfigured_source_returns_safe_service_unavailable_response():
    client = TestClient(create_app(provider=OfficialMCPProvider()))

    response = client.get("/api/v1/chart-context/NSE:NIFTY", params={"timeframe": "1h"})

    assert response.status_code == 503
    assert "No chart context was returned" in response.json()["detail"]


def test_oauth_start_requires_explicit_local_request_and_returns_authorization_url():
    client = TestClient(create_app(ReadyProvider(), ReadyOAuth()))

    response = client.post("/api/v1/oauth/official/start")

    assert response.status_code == 200
    assert response.json()["status"] == "awaiting_user"
    assert response.json()["authorization_url"] == "https://example.test/authorize"
