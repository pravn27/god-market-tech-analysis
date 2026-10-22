"""FastAPI application for the local, read-only MCP API service."""

import asyncio
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect

from .desktop_bridge import TradingViewDesktopWatchlistReader
from .desktop_candles import DesktopChartCandleProvider, FallbackChartProvider
from .global_market import GlobalMarketLiveSnapshotProvider, GlobalMarketSnapshotProvider, WatchlistGroupSource
from .global_market_live import GlobalMarketLiveHub, relay_global_market_live
from .models import (
    AnalysisTimeframe,
    ChartContext,
    GlobalMarketSnapshot,
    MtfInstrumentCatalog,
    MultiTimeframeAnalysis,
    MultiTimeframeCompleteness,
    MultiTimeframeContext,
    ServiceHealth,
)
from .mtf_analysis import MultiTimeframeAnalysisService, UnknownInstrumentError
from .mtf_live import MtfLiveHub, wait_for_client_disconnect
from .mtf_orchestrator import MultiTimeframeContextOrchestrator
from .oauth import OfficialMCPOAuthCoordinator
from .providers import ChartContextProvider, DataSourceUnavailableError, OfficialMCPProvider, normalize_timeframe
from .watchlist_source import DesktopWatchlistSectionSource, FallbackWatchlistSource, OfficialWatchlistSource


def create_app(
    provider: Optional[ChartContextProvider] = None,
    oauth: Optional[OfficialMCPOAuthCoordinator] = None,
    mtf_orchestrator: Optional[MultiTimeframeContextOrchestrator] = None,
    global_market_provider: Optional[GlobalMarketSnapshotProvider] = None,
    desktop_watchlist_reader: Optional[TradingViewDesktopWatchlistReader] = None,
    mtf_analysis: Optional[MultiTimeframeAnalysisService] = None,
    mtf_live: Optional[MtfLiveHub] = None,
    global_market_live: Optional[GlobalMarketLiveHub] = None,
    watchlist_source: Optional[WatchlistGroupSource] = None,
    desktop_candles: Optional[ChartContextProvider] = None,
) -> FastAPI:
    oauth_coordinator = oauth or OfficialMCPOAuthCoordinator()
    active_provider = provider or OfficialMCPProvider(tool_caller=oauth_coordinator)
    active_desktop_watchlist_reader = desktop_watchlist_reader or TradingViewDesktopWatchlistReader.from_environment()
    # Injected providers (tests, fixtures) never reach the Desktop fallbacks; they use only what was injected.
    # With the live official provider, the Desktop bridge is the fallback for both pages.
    active_desktop_candles = desktop_candles or DesktopChartCandleProvider.from_environment()
    active_mtf_provider = (
        FallbackChartProvider(active_provider, active_desktop_candles) if provider is None else active_provider
    )
    active_mtf_orchestrator = mtf_orchestrator or MultiTimeframeContextOrchestrator(active_mtf_provider)
    active_mtf_analysis = mtf_analysis or MultiTimeframeAnalysisService(active_mtf_orchestrator)
    active_mtf_live = mtf_live or MtfLiveHub(active_mtf_analysis, active_mtf_orchestrator)
    active_watchlist_source = watchlist_source or (
        FallbackWatchlistSource(
            OfficialWatchlistSource(oauth_coordinator),
            DesktopWatchlistSectionSource(active_desktop_watchlist_reader),
        )
        if provider is None
        else None
    )
    active_global_market_provider = global_market_provider or GlobalMarketLiveSnapshotProvider(
        active_provider,
        desktop_watchlist_reader=active_desktop_watchlist_reader,
        watchlist_source=active_watchlist_source,
    )
    active_global_market_live = global_market_live or GlobalMarketLiveHub(active_global_market_provider)
    app = FastAPI(
        title="God Market MCP API",
        version="0.1.0",
        description="Local, read-only TradingView context service for manual decision support.",
    )

    @app.get("/health", response_model=ServiceHealth, tags=["health"])
    async def health() -> ServiceHealth:
        return ServiceHealth(
            sources=[await active_provider.health(), await active_desktop_watchlist_reader.health()]
        )

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
        "/api/v1/mtf-analysis/instruments",
        response_model=MtfInstrumentCatalog,
        tags=["mtf-analysis"],
    )
    async def mtf_analysis_instruments() -> MtfInstrumentCatalog:
        return active_mtf_analysis.catalog

    @app.get(
        "/api/v1/mtf-analysis/{symbol}",
        response_model=MultiTimeframeAnalysis,
        tags=["mtf-analysis"],
    )
    async def mtf_analysis(
        symbol: str,
        refresh_mode: Literal["prefer_cache", "force_refresh"] = Query("prefer_cache"),
    ) -> MultiTimeframeAnalysis:
        try:
            return await active_mtf_analysis.analyze(symbol, force_refresh=refresh_mode == "force_refresh")
        except UnknownInstrumentError as error:
            raise HTTPException(status_code=422, detail=str(error))

    @app.websocket("/api/v1/mtf-analysis/{symbol}/live")
    async def mtf_analysis_live(websocket: WebSocket, symbol: str) -> None:
        normalized = symbol.strip().upper()
        if not active_mtf_analysis.is_known(normalized):
            await websocket.close(code=1008, reason="Unknown instrument.")
            return
        await websocket.accept()
        queue = active_mtf_live.subscribe(normalized)
        watcher = asyncio.create_task(wait_for_client_disconnect(websocket))
        getter: Optional[asyncio.Task] = None
        try:
            while not watcher.done():
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait(
                    {getter, watcher},
                    timeout=active_mtf_live.heartbeat_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if watcher.done():
                    break
                if getter in done:
                    envelope = getter.result()
                else:
                    getter.cancel()
                    envelope = active_mtf_live.heartbeat(normalized)
                await websocket.send_json(envelope.model_dump(mode="json"))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            watcher.cancel()
            if getter is not None and not getter.done():
                getter.cancel()
            active_mtf_live.unsubscribe(normalized, queue)

    @app.get(
        "/api/v1/global-market-sentiment",
        response_model=GlobalMarketSnapshot,
        tags=["global-market-sentiment"],
    )
    async def global_market_sentiment(
        timeframe: str = Query("1D", min_length=1, max_length=12),
    ) -> GlobalMarketSnapshot:
        try:
            interval = normalize_timeframe(timeframe)
        except DataSourceUnavailableError as error:
            raise HTTPException(status_code=422, detail=str(error))
        return await active_global_market_provider.get_snapshot(interval)

    @app.websocket("/api/v1/global-market-sentiment/live")
    async def global_market_sentiment_live(websocket: WebSocket) -> None:
        try:
            interval = normalize_timeframe(websocket.query_params.get("timeframe", "1D"))
        except DataSourceUnavailableError:
            await websocket.close(code=1008, reason="Unsupported timeframe.")
            return
        await websocket.accept()
        await relay_global_market_live(websocket, active_global_market_live, interval)

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
