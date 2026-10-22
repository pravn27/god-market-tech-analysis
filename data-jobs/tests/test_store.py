from datetime import datetime, timedelta

import pytest

from data_jobs.store import Bar, connect, to_text, transaction, upsert_bars
from support import NOW, UTC, bar


def _upsert(conn, bars, *, fetched_at=NOW):
    with transaction(conn):
        return upsert_bars(
            conn,
            symbol="DJI",
            timeframe="1W",
            bars=bars,
            source="fake",
            fetched_at=fetched_at,
        )


def test_connect_creates_the_tables_and_uses_wal_on_disk(tmp_path):
    conn = connect(tmp_path / "nested" / "jobs.sqlite3")
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"job_definitions", "job_runs", "job_items", "bars"} <= tables
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_new_bars_are_inserted_and_repeating_them_changes_nothing():
    conn = connect(":memory:")
    first = _upsert(conn, [bar(19), bar(20)])
    second = _upsert(conn, [bar(19), bar(20)])

    assert (first.inserted, first.updated, first.unchanged) == (2, 0, 0)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 2)
    assert conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0] == 2


def test_a_forming_bar_is_updated_when_it_closes():
    conn = connect(":memory:")
    _upsert(conn, [bar(26, close=100.0, is_closed=False)])
    counts = _upsert(conn, [bar(26, close=105.0, is_closed=True)], fetched_at=NOW + timedelta(days=2))

    assert (counts.inserted, counts.updated, counts.unchanged) == (0, 1, 0)
    row = conn.execute("SELECT close, is_closed, fetched_at FROM bars").fetchone()
    assert row["close"] == 105.0
    assert row["is_closed"] == 1
    assert row["fetched_at"] == to_text(NOW + timedelta(days=2))


def test_a_failed_batch_rolls_back_every_bar_in_it():
    conn = connect(":memory:")
    with pytest.raises(RuntimeError):
        with transaction(conn):
            upsert_bars(conn, symbol="DJI", timeframe="1W", bars=[bar(19), bar(20)], source="fake", fetched_at=NOW)
            raise RuntimeError("write failed midway")

    assert conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0] == 0


def test_bars_need_a_timezone_and_consistent_prices():
    with pytest.raises(ValueError, match="timezone"):
        Bar(bar_time=datetime(2026, 10, 19), open=1, high=2, low=0.5, close=1.5, volume=None, is_closed=True)
    with pytest.raises(ValueError, match="high"):
        Bar(bar_time=NOW, open=10, high=9, low=8, close=9.5, volume=None, is_closed=True)
    with pytest.raises(ValueError, match="finite"):
        Bar(bar_time=NOW, open=float("nan"), high=2, low=1, close=1.5, volume=None, is_closed=True)


def test_timestamps_sort_as_text_in_time_order():
    earlier = NOW
    later = NOW + timedelta(milliseconds=500)
    assert to_text(earlier) < to_text(later)
    assert to_text(NOW.astimezone(UTC)) == to_text(NOW)
