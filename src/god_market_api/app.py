"""FastAPI application for the local, read-only MCP API service."""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .models import ChartContext, ServiceHealth
from .oauth import OfficialMCPOAuthCoordinator
from .providers import ChartContextProvider, DataSourceUnavailableError, OfficialMCPProvider


def create_app(
    provider: Optional[ChartContextProvider] = None,
    oauth: Optional[OfficialMCPOAuthCoordinator] = None,
) -> FastAPI:
    active_provider = provider or OfficialMCPProvider()
    oauth_coordinator = oauth or OfficialMCPOAuthCoordinator()
    app = FastAPI(
        title="God Market MCP API",
        version="0.1.0",
        description="Local, read-only TradingView context service for manual decision support.",
    )

    @app.get("/health", response_model=ServiceHealth, tags=["health"])
    async def health() -> ServiceHealth:
        return ServiceHealth(sources=[await active_provider.health()])

    @app.get(
        "/api/v1/chart-context/{symbol}",
        response_model=ChartContext,
        tags=["chart-context"],
    )
    async def chart_context(
        symbol: str,
        timeframe: str = Query(..., min_length=1, max_length=12),
    ) -> ChartContext:
        try:
            return await active_provider.get_chart_context(symbol=symbol, timeframe=timeframe)
        except DataSourceUnavailableError as error:
            raise HTTPException(status_code=503, detail=str(error))

    @app.get("/api/v1/oauth/official/status", tags=["official-mcp-oauth"])
    async def official_oauth_status() -> dict:
        status = await oauth_coordinator.status()
        return {
            "status": status.status,
            "completed_at": status.completed_at,
            "tools_discovered": len(status.tools or []),
            "error": status.error,
        }

    @app.post("/api/v1/oauth/official/start", tags=["official-mcp-oauth"])
    async def start_official_oauth() -> dict:
        status = await oauth_coordinator.start()
        if status.error:
            raise HTTPException(status_code=502, detail="Unable to start the official MCP OAuth flow.")
        return {
            "status": status.status,
            "authorization_url": status.authorization_url,
            "message": "Open the authorization URL only after user approval.",
        }

    @app.get("/api/v1/oauth/official/callback", tags=["official-mcp-oauth"])
    async def official_oauth_callback(code: str, state: Optional[str] = None) -> dict:
        status = await oauth_coordinator.complete_callback(code=code, state=state)
        return {"status": status.status, "message": "Authorization callback accepted."}

    return app


app = create_app()
