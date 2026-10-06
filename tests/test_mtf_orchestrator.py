"""Integration-style unit tests for the multi-timeframe orchestration use case."""

import asyncio
from datetime import datetime, timezone

from god_market_api.models import (
    AnalysisTimeframe,
    ChartContext,
    DataSource,
    MultiTimeframeCompleteness,
    SourceState,
)
from god_market_api.mtf_orchestrator import MultiTimeframeContextOrchestrator
from god_market_api.providers import DataSourceUnavailableError


NOW = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)


class FixtureProvider:
    def __init__(self, unavailable_timeframes: set[str] | None = None) -> None:
        self.unavailable_timeframes = unavailable_timeframes or set()
        self.calls: list[str] = []

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        self.calls.append(timeframe)
        if timeframe in self.unavailable_timeframes:
            raise DataSourceUnavailableError(f"{timeframe} is temporarily unavailable")
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=NOW,
            freshness_state=SourceState.READY,
        )


class BlockingProvider(FixtureProvider):
    def __init__(self) -> None:
        super().__init__()
        self.active_requests = 0
        self.maximum_active_requests = 0
        self.request_limit_reached = asyncio.Event()
        self.all_timeframes_requested = asyncio.Event()
        self.release_requests = asyncio.Event()

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        self.calls.append(timeframe)
        if len(self.calls) >= 6:
            self.all_timeframes_requested.set()
        self.active_requests += 1
        self.maximum_active_requests = max(self.maximum_active_requests, self.active_requests)
        if self.active_requests >= 2:
            self.request_limit_reached.set()
        try:
            await self.release_requests.wait()
        finally:
            self.active_requests -= 1
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=NOW,
            freshness_state=SourceState.READY,
        )


def test_complete_fixture_returns_six_contexts_and_four_layer_views() -> None:
    provider = FixtureProvider()
    orchestrator = MultiTimeframeContextOrchestrator(provider, clock=lambda: NOW)

    result = asyncio.run(orchestrator.get_context("NSE:NIFTY"))

    assert result.completeness is MultiTimeframeCompleteness.COMPLETE
    assert len(result.contexts) == 6
    assert [layer.name for layer in result.layers] == ["Super TIDE", "TIDE", "WAVE", "Ripple / Super Ripple"]
    assert provider.calls.count("4h") == 1
    assert provider.calls.count("1h") == 1


def test_failed_15m_returns_partial_result_and_preserves_other_contexts() -> None:
    provider = FixtureProvider(unavailable_timeframes={"15m"})
    orchestrator = MultiTimeframeContextOrchestrator(provider, clock=lambda: NOW)

    result = asyncio.run(orchestrator.get_context("NSE:NIFTY"))

    assert result.completeness is MultiTimeframeCompleteness.PARTIAL
    assert result.contexts[AnalysisTimeframe.DAILY].context is not None
    unavailable = result.contexts[AnalysisTimeframe.FIFTEEN_MINUTE]
    assert unavailable.context is None
    assert unavailable.unavailable_reason == "15m is temporarily unavailable"


def test_fully_unavailable_fixture_returns_typed_unavailable_outcome() -> None:
    provider = FixtureProvider(
        unavailable_timeframes={"monthly", "weekly", "daily", "4h", "1h", "15m"}
    )
    orchestrator = MultiTimeframeContextOrchestrator(provider, clock=lambda: NOW)

    result = asyncio.run(orchestrator.get_context("NSE:NIFTY"))

    assert result.completeness is MultiTimeframeCompleteness.UNAVAILABLE
    assert all(entry.context is None and entry.unavailable_reason for entry in result.contexts.values())


def test_simultaneous_identical_refreshes_share_in_flight_requests() -> None:
    async def scenario() -> None:
        provider = BlockingProvider()
        orchestrator = MultiTimeframeContextOrchestrator(
            provider, clock=lambda: NOW, max_provider_concurrency=6
        )
        first = asyncio.create_task(orchestrator.get_context("NSE:NIFTY"))
        second = asyncio.create_task(orchestrator.get_context("NSE:NIFTY"))

        await asyncio.wait_for(provider.all_timeframes_requested.wait(), timeout=1)
        assert len(provider.calls) == 6
        assert len(set(provider.calls)) == 6

        provider.release_requests.set()
        first_result, second_result = await asyncio.gather(first, second)
        assert first_result.completeness is MultiTimeframeCompleteness.COMPLETE
        assert second_result.completeness is MultiTimeframeCompleteness.COMPLETE

    asyncio.run(scenario())


def test_provider_concurrency_limit_is_enforced() -> None:
    async def scenario() -> None:
        provider = BlockingProvider()
        orchestrator = MultiTimeframeContextOrchestrator(
            provider, clock=lambda: NOW, max_provider_concurrency=2
        )
        request = asyncio.create_task(orchestrator.get_context("NSE:NIFTY"))

        await asyncio.wait_for(provider.request_limit_reached.wait(), timeout=1)
        assert provider.maximum_active_requests == 2
        assert len(provider.calls) == 2

        provider.release_requests.set()
        result = await request
        assert result.completeness is MultiTimeframeCompleteness.COMPLETE
        assert provider.maximum_active_requests == 2

    asyncio.run(scenario())
