"""Centralized freshness policy for local multi-timeframe market context."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar, Mapping

from .models import AnalysisTimeframe


class CacheFreshness(str, Enum):
    """Whether cached source evidence is suitable for a decision view."""

    FRESH = "fresh"
    STALE = "stale"
    EXPIRED = "expired"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class FreshnessWindow:
    """Time limits measured from the source-provided latest candle timestamp."""

    fresh_for: timedelta
    stale_for: timedelta

    def __post_init__(self) -> None:
        if self.fresh_for < timedelta(0) or self.stale_for < self.fresh_for:
            raise ValueError("Freshness windows must be non-negative and stale_for must not precede fresh_for.")


@dataclass(frozen=True)
class FreshnessPolicy:
    """Configurable cache policy, kept separate from trading and setup rules."""

    fresh_for: timedelta
    stale_for: timedelta
    timeframe_windows: Mapping[AnalysisTimeframe, FreshnessWindow] = field(default_factory=dict)

    _DEFAULT: ClassVar["FreshnessPolicy | None"] = None

    def __post_init__(self) -> None:
        FreshnessWindow(self.fresh_for, self.stale_for)

    def for_timeframe(self, timeframe: AnalysisTimeframe) -> FreshnessWindow:
        return self.timeframe_windows.get(timeframe, FreshnessWindow(self.fresh_for, self.stale_for))

    @classmethod
    def defaults(cls) -> "FreshnessPolicy":
        """Return the shared, intentionally conservative initial policy."""
        if cls._DEFAULT is None:
            cls._DEFAULT = cls(
                fresh_for=timedelta(hours=36),
                stale_for=timedelta(hours=72),
                timeframe_windows={
                    AnalysisTimeframe.MONTHLY: FreshnessWindow(timedelta(days=40), timedelta(days=70)),
                    AnalysisTimeframe.WEEKLY: FreshnessWindow(timedelta(days=9), timedelta(days=16)),
                    AnalysisTimeframe.DAILY: FreshnessWindow(timedelta(hours=36), timedelta(hours=72)),
                    AnalysisTimeframe.FOUR_HOUR: FreshnessWindow(timedelta(hours=6), timedelta(hours=14)),
                    AnalysisTimeframe.ONE_HOUR: FreshnessWindow(timedelta(hours=2), timedelta(hours=5)),
                    AnalysisTimeframe.FIFTEEN_MINUTE: FreshnessWindow(timedelta(minutes=35), timedelta(hours=2)),
                },
            )
        return cls._DEFAULT


def classify_freshness(
    timeframe: AnalysisTimeframe,
    source_timestamp: datetime | None,
    *,
    now: datetime,
    policy: FreshnessPolicy,
) -> CacheFreshness:
    """Classify source evidence without issuing a provider request."""
    if source_timestamp is None:
        return CacheFreshness.UNAVAILABLE
    if source_timestamp.tzinfo is None or now.tzinfo is None:
        raise ValueError("Freshness timestamps must be timezone-aware.")

    age = now.astimezone(timezone.utc) - source_timestamp.astimezone(timezone.utc)
    window = policy.for_timeframe(timeframe)
    if age <= window.fresh_for:
        return CacheFreshness.FRESH
    if age <= window.stale_for:
        return CacheFreshness.STALE
    return CacheFreshness.EXPIRED
