"""One-time move of stored daily bars from their UTC stamps to their trading days.

Bars already stored under the old UTC stamps are re-stamped with the same rule new runs use. The
symbol's derived weekly, monthly and quarterly bars are then rebuilt from the re-stamped daily bars.
Each symbol is handled in its own transaction, so a failure leaves that symbol's rows unchanged.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Callable, Iterable, Sequence

from .runner import DAILY_TIMEFRAME, DERIVED_SOURCE, _write_derived, on_trading_days
from .store import Bar, from_text, to_text, transaction


def rekey_daily_bars(
    conn: sqlite3.Connection,
    *,
    symbols: Iterable[str],
    periods: Sequence[str],
    trading_day: Callable[[str, datetime], datetime],
    now: datetime,
) -> dict:
    """Returns the number of daily bars re-stamped per symbol."""
    moved = {}
    for symbol in symbols:
        with transaction(conn):
            rows = conn.execute(
                "SELECT bar_time, open, high, low, close, volume, is_closed, source, fetched_at FROM bars "
                "WHERE symbol = ? AND timeframe = ? ORDER BY bar_time",
                (symbol, DAILY_TIMEFRAME),
            ).fetchall()
            if not rows:
                moved[symbol] = 0
                continue
            stored = [
                Bar(
                    bar_time=from_text(row["bar_time"]),
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                    is_closed=bool(row["is_closed"]),
                )
                for row in rows
            ]
            # Raises before anything is deleted if two stored bars would land on one trading day.
            restamped = on_trading_days(stored, symbol=symbol, trading_day=trading_day, now=now)
            conn.execute("DELETE FROM bars WHERE symbol = ? AND timeframe = ?", (symbol, DAILY_TIMEFRAME))
            for bar, row in zip(restamped, rows):
                conn.execute(
                    "INSERT INTO bars (symbol, timeframe, bar_time, open, high, low, close, volume, is_closed, source, fetched_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        symbol,
                        DAILY_TIMEFRAME,
                        to_text(bar.bar_time),
                        bar.open,
                        bar.high,
                        bar.low,
                        bar.close,
                        bar.volume,
                        int(bar.is_closed),
                        row["source"],
                        row["fetched_at"],
                    ),
                )
            if periods:
                conn.execute(
                    f"DELETE FROM bars WHERE symbol = ? AND source = ? AND timeframe IN ({','.join('?' * len(periods))})",
                    (symbol, DERIVED_SOURCE, *periods),
                )
                _write_derived(conn, symbol, periods, now)
            moved[symbol] = len(restamped)
    return moved
