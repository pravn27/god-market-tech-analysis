"""Shared test helpers: bar factory, fake fetcher, and a clock the tests move by hand."""

from datetime import datetime, timezone
from typing import Dict, List, Sequence, Tuple

from data_jobs.runner import FetchResult
from data_jobs.store import Bar

UTC = timezone.utc
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def bar(day: int, close: float = 100.0, *, is_closed: bool = True, volume: float | None = None) -> Bar:
    return Bar(
        bar_time=datetime(2026, 10, day, tzinfo=UTC),
        open=99.0,
        high=max(99.0, close) + 1.0,
        low=98.0,
        close=close,
        volume=volume,
        is_closed=is_closed,
    )


def default_bars() -> List[Bar]:
    return [bar(19), bar(20)]


class FakeFetcher:
    """Returns canned bars per (symbol, timeframe). Keys in ``failing`` raise; keys in ``bars`` can be empty."""

    def __init__(
        self,
        bars: Dict[Tuple[str, str], List[Bar]] | None = None,
        failing: Sequence[Tuple[str, str]] = (),
        source: str = "fake",
    ) -> None:
        self.bars = bars or {}
        self.failing = set(failing)
        self.source = source
        self.calls: List[Tuple[str, str, int]] = []

    def fetch(self, symbol: str, timeframe: str, *, count: int) -> FetchResult:
        self.calls.append((symbol, timeframe, count))
        if (symbol, timeframe) in self.failing:
            raise ConnectionError("source unreachable")
        return FetchResult(
            bars=list(self.bars.get((symbol, timeframe), default_bars())),
            source=self.source,
        )


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now
