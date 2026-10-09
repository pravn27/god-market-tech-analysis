"""HTTP contract tests for the multi-timeframe checklist endpoints (fixture provider only)."""

import asyncio
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from god_market_api.app import create_app
from god_market_api.models import (
    AnalysisTimeframe as TF,
    ChartContext,
    DataSource,
    MultiTimeframeCompleteness,
    MultiTimeframeContext,
    SourceHealth,
    SourceState,
    TimeframeContextResult,
)
from god_market_api.mtf_analysis import (
    STALE_REASON,
    MultiTimeframeAnalysisService,
    is_live_candle,
    load_instrument_catalog,
)
from god_market_api.providers import DataSourceUnavailableError

from test_mtf_checklist import make_candles


class ChecklistFixtureProvider:
    def __init__(self, unavailable: frozenset[str] = frozenset()) -> None:
        self.unavailable = unavailable
        self.calls: list[tuple[str, str]] = []

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source=DataSource.OFFICIAL_MCP,
            state=SourceState.READY,
            detail="Test provider is ready.",
            checked_at=datetime.now(timezone.utc),
        )

    async def get_chart_context(self, symbol: str, timeframe: str) -> ChartContext:
        self.calls.append((symbol, timeframe))
        if timeframe in self.unavailable:
            raise DataSourceUnavailableError("Source is unavailable for this timeframe.")
        candles = make_candles()
        return ChartContext(
            symbol=symbol,
            timeframe=timeframe,
            source=DataSource.OFFICIAL_MCP,
            source_timestamp=candles[-1].timestamp,
            freshness_state=SourceState.READY,
            candles=candles,
        )


def client_for(provider: ChecklistFixtureProvider) -> TestClient:
    return TestClient(create_app(provider=provider))


def test_instruments_endpoint_returns_watchlist_sections_in_order() -> None:
    response = client_for(ChecklistFixtureProvider()).get("/api/v1/mtf-analysis/instruments")

    assert response.status_code == 200
    payload = response.json()
    assert payload["watchlist_name"] == "PS_DailyWatch_Favourite"
    assert payload["default_symbol"] == "NSE:NIFTY"
    assert [section["name"] for section in payload["sections"]] == [
        "LONG / MEDIUM TERM INVESTMENT",
        "F & O",
        "DAILY_WATCHLIST 2024 JAN",
        "STOCKS WATCHLIST",
    ]
    fo = payload["sections"][1]["instruments"]
    assert fo[0] == {"symbol": "NSE:NIFTY", "display_name": "Nifty 50"}


def test_snapshot_has_no_invisible_characters_in_section_names() -> None:
    for section in load_instrument_catalog().sections:
        assert section.name.isprintable()
        assert not section.name.startswith("#")


def test_analysis_returns_complete_checklist_for_nifty() -> None:
    provider = ChecklistFixtureProvider()
    response = client_for(provider).get("/api/v1/mtf-analysis/NSE:NIFTY")

    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "NSE:NIFTY"
    assert payload["display_name"] == "Nifty 50"
    assert payload["profile_version"] == "mtf-checklist-v1"
    assert payload["completeness"] == "complete"
    assert set(payload["timeframes"]) == {"monthly", "weekly", "daily", "4h", "1h", "15m"}
    assert sorted(tf for _, tf in provider.calls) == sorted(tf.value for tf in TF)
    assert [layer["name"] for layer in payload["layers"]] == ["Super TIDE", "TIDE", "WAVE", "RIPPLE"]
    assert len(payload["decisions"]["double_screens"]) == 3
    assert "not financial advice" in payload["decisions"]["disclaimer"]

    rows = {row["id"]: row for row in payload["rows"]}
    assert set(rows["macd"]["cells"]) == set(payload["timeframes"])
    assert rows["macd"]["cells"]["daily"]["labels"]
    assert rows["what_if"]["automated"] is False
    assert rows["what_if"]["cells"] == {}


def test_analysis_marks_missing_timeframe_and_incomplete_decision() -> None:
    provider = ChecklistFixtureProvider(unavailable=frozenset({"15m"}))
    payload = client_for(provider).get("/api/v1/mtf-analysis/NSE:NIFTY").json()

    assert payload["completeness"] == "partial"
    assert payload["timeframes"]["15m"]["freshness_state"] == "unavailable"
    assert payload["timeframes"]["15m"]["unavailable_reason"]
    rsi_15m = next(row for row in payload["rows"] if row["id"] == "rsi")["cells"]["15m"]
    assert rsi_15m["bias"] == "unavailable"
    assert payload["decisions"]["triple_screen"]["decision"] == "INCOMPLETE — 15m unavailable"
    assert payload["decisions"]["double_screens"][0]["decision"] != "INCOMPLETE — 15m unavailable"
    assert any(warning.startswith("15m:") for warning in payload["warnings"])


def test_analysis_with_no_data_is_unavailable_but_still_typed() -> None:
    provider = ChecklistFixtureProvider(unavailable=frozenset(tf.value for tf in TF))
    response = client_for(provider).get("/api/v1/mtf-analysis/NSE:NIFTY")

    assert response.status_code == 200
    assert response.json()["completeness"] == "unavailable"


def test_symbol_outside_snapshot_is_rejected() -> None:
    provider = ChecklistFixtureProvider()
    response = client_for(provider).get("/api/v1/mtf-analysis/NSE:TCS")

    assert response.status_code == 422
    assert "PS_DailyWatch_Favourite" in response.json()["detail"]
    assert provider.calls == []


def test_symbol_is_case_insensitive() -> None:
    response = client_for(ChecklistFixtureProvider()).get("/api/v1/mtf-analysis/nse:reliance")
    assert response.status_code == 200
    assert response.json()["symbol"] == "NSE:RELIANCE"


def test_invalid_refresh_mode_is_rejected() -> None:
    response = client_for(ChecklistFixtureProvider()).get(
        "/api/v1/mtf-analysis/NSE:NIFTY", params={"refresh_mode": "always"}
    )
    assert response.status_code == 422


class StaleOnceOrchestrator:
    """Serves a stale 1h context from cache, then a fresh one when forced."""

    def __init__(self, refresh_succeeds: bool) -> None:
        self.refresh_succeeds = refresh_succeeds
        self.forced: list[list[TF]] = []

    async def get_context(self, symbol, *, timeframes=None, force_refresh=False):
        results = {}
        for tf in timeframes:
            candles = make_candles()
            stale = tf is TF.ONE_HOUR and not (force_refresh and self.refresh_succeeds)
            if force_refresh and tf is TF.ONE_HOUR and not self.refresh_succeeds:
                results[tf] = TimeframeContextResult(timeframe=tf, unavailable_reason="Refresh failed.")
                continue
            results[tf] = TimeframeContextResult(
                timeframe=tf,
                context=ChartContext(
                    symbol=symbol,
                    timeframe=tf.value,
                    source=DataSource.OFFICIAL_MCP,
                    source_timestamp=candles[-1].timestamp,
                    freshness_state=SourceState.STALE if stale else SourceState.READY,
                    candles=candles,
                ),
            )
        if force_refresh:
            self.forced.append(list(timeframes))
        return MultiTimeframeContext(
            symbol=symbol,
            requested_at=datetime.now(timezone.utc),
            completeness=MultiTimeframeCompleteness.COMPLETE,
            contexts=results,
        )


def test_stale_timeframe_is_refreshed_once() -> None:
    orchestrator = StaleOnceOrchestrator(refresh_succeeds=True)
    result = asyncio.run(MultiTimeframeAnalysisService(orchestrator).analyze("NSE:NIFTY"))

    assert orchestrator.forced == [[TF.ONE_HOUR]]
    assert result.timeframes[TF.ONE_HOUR].freshness_state is SourceState.READY
    assert result.completeness is MultiTimeframeCompleteness.COMPLETE


def test_stale_timeframe_that_cannot_refresh_is_unavailable() -> None:
    orchestrator = StaleOnceOrchestrator(refresh_succeeds=False)
    result = asyncio.run(MultiTimeframeAnalysisService(orchestrator).analyze("NSE:NIFTY"))

    status = result.timeframes[TF.ONE_HOUR]
    assert status.freshness_state is SourceState.STALE
    assert status.unavailable_reason == STALE_REASON
    assert result.completeness is MultiTimeframeCompleteness.PARTIAL
    assert result.decisions.triple_screen.decision == "INCOMPLETE — 1h unavailable"


def test_live_candle_detection() -> None:
    now = datetime(2026, 10, 9, 10, 20, tzinfo=timezone.utc)
    assert is_live_candle(TF.FIFTEEN_MINUTE, datetime(2026, 10, 9, 10, 15, tzinfo=timezone.utc), now)
    assert not is_live_candle(TF.FIFTEEN_MINUTE, datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc), now)
    assert is_live_candle(TF.MONTHLY, datetime(2026, 10, 1, tzinfo=timezone.utc), now)
    assert not is_live_candle(TF.MONTHLY, datetime(2026, 9, 1, tzinfo=timezone.utc), now)
