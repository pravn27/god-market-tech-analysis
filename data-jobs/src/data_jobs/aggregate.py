"""Weekly, monthly and quarterly bars built from stored daily bars.

For each period:
- open is the first trading day's open
- high is the highest high in the period
- low is the lowest low in the period
- close is the last trading day's close
- volume is the sum of the daily volumes, left blank if any day has no volume (an understated total
  would be wrong)

Bar times are the period's start (Monday for a week, the 1st for a month or quarter, in UTC). A
holiday that removes a period's first day therefore does not move the bar's key, so reruns update the
same row instead of adding a duplicate.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Dict, List, Sequence

from .store import Bar

WEEKLY = "1W"
MONTHLY = "1M"
QUARTERLY = "3M"
PERIODS = (WEEKLY, MONTHLY, QUARTERLY)


def period_start(day: date, period: str) -> date:
    if period == WEEKLY:
        return day - timedelta(days=day.weekday())
    if period == MONTHLY:
        return day.replace(day=1)
    if period == QUARTERLY:
        return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    raise ValueError(f"Unsupported period: {period}")


def next_period_start(start: date, period: str) -> date:
    if period == WEEKLY:
        return start + timedelta(days=7)
    if period == MONTHLY:
        months = 1
    elif period == QUARTERLY:
        months = 3
    else:
        raise ValueError(f"Unsupported period: {period}")
    month_index = start.month - 1 + months
    return date(start.year + month_index // 12, month_index % 12 + 1, 1)


def aggregate(daily: Sequence[Bar], period: str, *, now: datetime) -> List[Bar]:
    """Group daily bars into periods. A period is final once its next period has started."""
    if period not in PERIODS:
        raise ValueError(f"Unsupported period: {period}")
    groups: Dict[date, List[Bar]] = {}
    seen_days = set()
    for bar in sorted(daily, key=lambda item: item.bar_time):
        day = bar.bar_time.astimezone(timezone.utc).date()
        if day in seen_days:
            raise ValueError(f"Two daily bars fall on {day.isoformat()}; the daily series must have one bar per day.")
        seen_days.add(day)
        groups.setdefault(period_start(day, period), []).append(bar)

    result: List[Bar] = []
    for start in sorted(groups):
        bars = groups[start]
        volumes = [bar.volume for bar in bars]
        volume = sum(volumes) if all(volume is not None for volume in volumes) else None
        period_end = datetime.combine(next_period_start(start, period), time(0), tzinfo=timezone.utc)
        result.append(
            Bar(
                bar_time=datetime.combine(start, time(0), tzinfo=timezone.utc),
                open=bars[0].open,
                high=max(bar.high for bar in bars),
                low=min(bar.low for bar in bars),
                close=bars[-1].close,
                volume=volume,
                is_closed=period_end <= now,
            )
        )
    return result
