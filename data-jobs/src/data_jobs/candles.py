"""Converts daily candles from a market-data source into stored bars."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Sequence

from god_market_api.models import Candle

from .store import Bar


def daily_bars(candles: Sequence[Candle], *, count: int, now: datetime) -> List[Bar]:
    """The most recent ``count`` daily candles as bars. A day is final once it has passed."""
    bars: List[Bar] = []
    for candle in candles[-count:]:
        bars.append(
            Bar(
                bar_time=candle.timestamp,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                is_closed=candle.timestamp + timedelta(days=1) <= now,
            )
        )
    return bars
