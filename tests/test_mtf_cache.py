"""Contract tests for the local multi-timeframe context cache."""

from datetime import datetime, timedelta, timezone

from god_market_api.models import AnalysisTimeframe, ChartContext, DataSource, SourceState
from god_market_api.mtf_cache import LocalContextCache
from god_market_api.mtf_policy import CacheFreshness, FreshnessPolicy


NOW = datetime(2026, 10, 6, 9, 0, tzinfo=timezone.utc)


def context(*, source_timestamp: datetime = NOW) -> ChartContext:
    return ChartContext(
        symbol="NSE:NIFTY",
        timeframe="1D",
        source=DataSource.OFFICIAL_MCP,
        source_timestamp=source_timestamp,
        freshness_state=SourceState.READY,
    )


def policy() -> FreshnessPolicy:
    return FreshnessPolicy(
        fresh_for=timedelta(minutes=5),
        stale_for=timedelta(minutes=15),
    )


def test_valid_cached_context_is_reused_without_a_provider_request() -> None:
    cache = LocalContextCache(policy=policy(), clock=lambda: NOW)
    cache.put(AnalysisTimeframe.DAILY, context())

    lookup = cache.get(DataSource.OFFICIAL_MCP, "nse:nifty", AnalysisTimeframe.DAILY)

    assert lookup.freshness is CacheFreshness.FRESH
    assert lookup.context is not None
    assert lookup.context.symbol == "NSE:NIFTY"


def test_cache_freshness_is_deterministic_against_the_injected_clock() -> None:
    cache = LocalContextCache(policy=policy(), clock=lambda: NOW)
    cache.put(AnalysisTimeframe.DAILY, context(source_timestamp=NOW - timedelta(minutes=6)))

    stale = cache.get(DataSource.OFFICIAL_MCP, "NSE:NIFTY", AnalysisTimeframe.DAILY)
    expired = cache.get(
        DataSource.OFFICIAL_MCP,
        "NSE:NIFTY",
        AnalysisTimeframe.DAILY,
        now=NOW + timedelta(minutes=10),
    )

    assert stale.freshness is CacheFreshness.STALE
    assert stale.context is not None
    assert expired.freshness is CacheFreshness.EXPIRED
    assert expired.context is None


def test_missing_cache_entry_has_a_typed_unavailable_outcome() -> None:
    cache = LocalContextCache(policy=policy(), clock=lambda: NOW)

    lookup = cache.get(DataSource.OFFICIAL_MCP, "NSE:NIFTY", AnalysisTimeframe.DAILY)

    assert lookup.freshness is CacheFreshness.UNAVAILABLE
    assert lookup.context is None


def test_cache_policy_is_centralized_and_not_embedded_in_contexts() -> None:
    first = FreshnessPolicy.defaults()
    second = FreshnessPolicy.defaults()

    assert first is second
    assert first.for_timeframe(AnalysisTimeframe.FIFTEEN_MINUTE).fresh_for < first.for_timeframe(
        AnalysisTimeframe.DAILY
    ).fresh_for
