"""SQLite store for market bars and job telemetry.

Every timestamp is UTC text in one fixed format, so text comparison matches time order.
"""

from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence, Union

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
MEMORY = ":memory:"

SCHEMA = """
CREATE TABLE IF NOT EXISTS job_definitions (
    name TEXT PRIMARY KEY,
    interval_seconds INTEGER NOT NULL CHECK (interval_seconds > 0),
    next_run_at TEXT,
    last_success_at TEXT
);

CREATE TABLE IF NOT EXISTS job_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name TEXT NOT NULL,
    period_key TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'partial', 'failed', 'stalled')),
    started_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    finished_at TEXT,
    items_total INTEGER NOT NULL DEFAULT 0,
    bars_inserted INTEGER NOT NULL DEFAULT 0,
    bars_updated INTEGER NOT NULL DEFAULT 0,
    bars_unchanged INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS job_runs_by_job ON job_runs (job_name, id);
CREATE INDEX IF NOT EXISTS job_runs_by_period ON job_runs (job_name, period_key);

CREATE TABLE IF NOT EXISTS job_items (
    run_id INTEGER NOT NULL REFERENCES job_runs (id),
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'succeeded', 'failed')),
    fetched_at TEXT,
    error TEXT,
    PRIMARY KEY (run_id, symbol, timeframe)
);

CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL,
    is_closed INTEGER NOT NULL CHECK (is_closed IN (0, 1)),
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (symbol, timeframe, bar_time)
);
"""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def to_text(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timestamps must include a timezone.")
    return value.astimezone(timezone.utc).strftime(TIME_FORMAT)


def from_text(value: str) -> datetime:
    return datetime.strptime(value, TIME_FORMAT).replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Bar:
    bar_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Union[float, None]
    is_closed: bool

    def __post_init__(self) -> None:
        if self.bar_time.tzinfo is None:
            raise ValueError("Bar time must include a timezone.")
        prices = (self.open, self.high, self.low, self.close)
        if not all(math.isfinite(price) for price in prices):
            raise ValueError("Bar prices must be finite numbers.")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("Bar high must be at least the open, close and low.")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("Bar low must be at most the open, close and high.")


@dataclass(frozen=True)
class UpsertCounts:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def connect(path: Union[str, Path]) -> sqlite3.Connection:
    """Open the store, create any missing tables, and use WAL so readers do not block the writer."""
    location = str(path)
    on_disk = location != MEMORY
    if on_disk:
        Path(location).parent.mkdir(parents=True, exist_ok=True)
    # Autocommit mode: transactions are opened and closed explicitly by ``transaction``.
    conn = sqlite3.connect(location, isolation_level=None, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if on_disk:
        conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(SCHEMA)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Write lock for the block: commit on success, roll back on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def upsert_bars(
    conn: sqlite3.Connection,
    *,
    symbol: str,
    timeframe: str,
    bars: Sequence[Bar],
    source: str,
    fetched_at: datetime,
) -> UpsertCounts:
    """Insert new bars, update changed ones, and refresh ``fetched_at`` on every bar it confirms.

    Call inside ``transaction`` so one failed batch leaves no partial rows behind.
    """
    stamp = to_text(fetched_at)
    inserted = updated = unchanged = 0
    for bar in bars:
        key = to_text(bar.bar_time)
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume, int(bar.is_closed))
        row = conn.execute(
            "SELECT open, high, low, close, volume, is_closed FROM bars "
            "WHERE symbol = ? AND timeframe = ? AND bar_time = ?",
            (symbol, timeframe, key),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO bars (symbol, timeframe, bar_time, open, high, low, close, volume, is_closed, source, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (symbol, timeframe, key, *values, source, stamp),
            )
            inserted += 1
            continue
        if tuple(row) == values:
            unchanged += 1
        else:
            updated += 1
        conn.execute(
            "UPDATE bars SET open = ?, high = ?, low = ?, close = ?, volume = ?, is_closed = ?, source = ?, fetched_at = ? "
            "WHERE symbol = ? AND timeframe = ? AND bar_time = ?",
            (*values, source, stamp, symbol, timeframe, key),
        )
    return UpsertCounts(inserted=inserted, updated=updated, unchanged=unchanged)
