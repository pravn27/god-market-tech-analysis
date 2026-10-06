"""FastAPI application for the local, read-only MCP API service."""

from typing import Optional

from fastapi import FastAPI, HTTPException, Query

from .global_market import GlobalMarketLiveSnapshotProvider, GlobalMarketSnapshotProvider
from .models import (
    AnalysisTimeframe,
    ChartContext,
    GlobalMarketSnapshot,
    MultiTimeframeCompleteness,
    MultiTimeframeContext,
    ServiceHealth,
)
from .mtf_orchestrator import MultiTimeframeContextOrchestrator
from .oauth import OfficialMCPOAuthCoordinator
from .providers import ChartContextProvider, DataSourceUnavailableError, OfficialMCPProvider


def create_app(
    provider: Optional[ChartContextProvider] = None,
    oauth: Optional[OfficialMCPOAuthCoordinator] = None,
    mtf_orchestrator: Optional[MultiTimeframeContextOrchestrator] = None,
    global_market_provider: Optional[GlobalMarketSnapshotProvider] = None,
) -> FastAPI:
    oauth_coordinator = oauth or OfficialMCPOAuthCoordinator()
    active_provider = provider or OfficialMCPProvider(tool_caller=oauth_coordinator)
    active_mtf_orchestrator = mtf_orchestrator or MultiTimeframeContextOrchestrator(active_provider)
    active_global_market_provider = global_market_provider or GlobalMarketLiveSnapshotProvider(active_provider)
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

    @app.get(
        "/api/v1/multi-timeframe-context/{symbol}",
        response_model=MultiTimeframeContext,
        tags=["multi-timeframe-context"],
    )
    async def multi_timeframe_context(
        symbol: str,
        timeframe: list[AnalysisTimeframe] | None = Query(default=None, alias="timeframe"),
    ) -> MultiTimeframeContext:
        result = await active_mtf_orchestrator.get_context(symbol, timeframes=timeframe)
        if result.completeness is MultiTimeframeCompleteness.UNAVAILABLE:
            raise HTTPException(
                status_code=503,
                detail={
                    "message": "No usable market context is currently available. Check source authorization or retry later.",
                    "result": result.model_dump(mode="json"),
                },
            )
        return result

    @app.get(
        "/api/v1/global-market-sentiment",
        response_model=GlobalMarketSnapshot,
        tags=["global-market-sentiment"],
    )
    async def global_market_sentiment(
        timeframe: str = Query("daily", min_length=1, max_length=12),
    ) -> GlobalMarketSnapshot:
        return await active_global_market_provider.get_snapshot(timeframe)

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
