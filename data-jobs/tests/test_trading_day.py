from datetime import datetime, timedelta, timezone

import pytest

from data_jobs.rekey import rekey_daily_bars
from data_jobs.runner import JobSpec, on_trading_days, run_job
from data_jobs.store import Bar, connect, to_text, upsert_bars
from data_jobs.trading_day import UnknownSessionZone, trading_day
from support import NOW, UTC, FakeFetcher, FixedClock

FUTURES_STAMP = datetime(2026, 10, 21, 22, 0, tzinfo=UTC)  # 18:00 New York, the 22 Oct session


def _utc_midnight(day):
    return datetime(2026, 10, day, tzinfo=UTC)


def test_an_evening_open_futures_session_trades_on_the_next_local_day():
    assert trading_day("BLACKBULL:US30", FUTURES_STAMP) == _utc_midnight(22)
    assert trading_day("BLACKBULL:DJ30.F", FUTURES_STAMP) == _utc_midnight(22)


def test_futures_after_the_us_clocks_change_still_land_on_the_trading_day():
    # After the US clocks change: the session that opens 22 Nov 23:00Z (18:00 New York) trades on 23 Nov.
    assert trading_day("BLACKBULL:US30", datetime(2026, 11, 22, 23, 0, tzinfo=UTC)) == datetime(2026, 11, 23, tzinfo=UTC)


def test_a_morning_open_index_keeps_its_own_day():
    assert trading_day("TVC:SPX", datetime(2026, 10, 22, 13, 30, tzinfo=UTC)) == _utc_midnight(22)


def test_asia_and_europe_morning_sessions_keep_their_own_day():
    assert trading_day("TVC:NI225", datetime(2026, 10, 22, 0, 0, tzinfo=UTC)) == _utc_midnight(22)
    assert trading_day("XETR:DAX", datetime(2026, 10, 22, 7, 0, tzinfo=UTC)) == _utc_midnight(22)


def test_midnight_utc_stamps_of_an_evening_session_map_to_the_same_trading_day():
    # The DXY series also carries 00:00Z stamps (19:00 New York the evening before): they are the same day.
    assert trading_day("TVC:DXY", datetime(2025, 11, 4, 0, 0, tzinfo=UTC)) == datetime(2025, 11, 4, tzinfo=UTC)


def test_a_morning_session_in_the_afternoon_keeps_its_own_day():
    # Diwali 2025: NSE's Muhurat session ran at 08:00Z (13:30 IST) on 21 Oct, the day with no regular session.
    muhurat = datetime(2025, 10, 21, 8, 0, tzinfo=UTC)
    regular = datetime(2025, 10, 22, 0, 45, tzinfo=UTC)

    assert trading_day("NSEIX:NIFTY1!", muhurat) == datetime(2025, 10, 21, tzinfo=UTC)
    bars = [
        Bar(muhurat, 99, 101, 98, 100, None, True),
        Bar(regular, 99, 101, 98, 100, None, True),
    ]
    days = [bar.bar_time for bar in on_trading_days(bars, symbol="NSEIX:NIFTY1!", trading_day=trading_day, now=NOW)]
    assert days == [datetime(2025, 10, 21, tzinfo=UTC), datetime(2025, 10, 22, tzinfo=UTC)]


def test_symbol_lookup_ignores_case():
    assert trading_day("tvc:spx", datetime(2026, 10, 22, 13, 30, tzinfo=UTC)) == _utc_midnight(22)


def test_a_symbol_without_an_exchange_zone_is_refused():
    with pytest.raises(UnknownSessionZone, match="No exchange time zone is set for NYSE:NEW"):
        trading_day("NYSE:NEW", datetime(2026, 10, 22, 13, 30, tzinfo=UTC))


def test_restamped_daily_bars_recompute_whether_they_are_final():
    bars = [Bar(FUTURES_STAMP, 99, 101, 98, 100, None, False)]

    (restamped,) = on_trading_days(bars, symbol="BLACKBULL:US30", trading_day=trading_day, now=NOW)

    assert restamped.bar_time == _utc_midnight(22)
    assert restamped.is_closed is False  # the 22 Oct session ends after NOW (22 Oct 12:00 UTC)


def test_two_bars_that_land_on_one_trading_day_are_refused():
    bars = [
        Bar(datetime(2026, 10, 21, 22, 0, tzinfo=UTC), 99, 101, 98, 100, None, True),
        Bar(datetime(2026, 10, 22, 0, 0, tzinfo=UTC), 99, 101, 98, 100, None, True),
    ]

    with pytest.raises(ValueError, match="same trading day, 2026-10-22"):
        on_trading_days(bars, symbol="BLACKBULL:US30", trading_day=trading_day, now=NOW)


def test_a_run_stores_daily_bars_under_their_trading_day():
    conn = connect(":memory:")
    spec = JobSpec(
        name="gm-daily",
        interval=timedelta(days=1),
        symbols=("BLACKBULL:US30",),
        timeframes=("1D",),
        bar_count=5,
        trading_day=trading_day,
    )
    fetcher = FakeFetcher({("BLACKBULL:US30", "1D"): [Bar(FUTURES_STAMP, 99, 101, 98, 100, None, True)]})

    run_job(conn, spec, fetcher, clock=FixedClock(NOW))

    stored = conn.execute("SELECT bar_time FROM bars WHERE symbol = 'BLACKBULL:US30'").fetchall()
    assert [row["bar_time"] for row in stored] == [to_text(_utc_midnight(22))]


def test_rekeying_moves_stored_utc_stamps_to_trading_days_and_rebuilds_the_weekly_bars():
    conn = connect(":memory:")
    old = [
        Bar(datetime(2026, 10, day - 1, 22, 0, tzinfo=UTC), 99, 101, 98, 100, None, True)
        for day in range(6, 23)  # trading days Tue 6 Oct to Thu 22 Oct, stored at the previous evening's 22:00Z
    ]
    upsert_bars(conn, symbol="BLACKBULL:US30", timeframe="1D", bars=old, source="desktop_bridge", fetched_at=NOW)

    moved = rekey_daily_bars(
        conn,
        symbols=["BLACKBULL:US30"],
        periods=("1W",),
        trading_day=trading_day,
        now=NOW,
    )

    assert moved == {"BLACKBULL:US30": 17}
    daily = conn.execute("SELECT bar_time, source FROM bars WHERE timeframe = '1D' ORDER BY bar_time").fetchall()
    assert daily[0]["bar_time"] == to_text(_utc_midnight(6))
    assert daily[-1]["bar_time"] == to_text(_utc_midnight(22))
    assert {row["source"] for row in daily} == {"desktop_bridge"}  # the source of each bar is kept
    weekly = conn.execute("SELECT bar_time FROM bars WHERE timeframe = '1W' ORDER BY bar_time").fetchall()
    # History starts on Tue 6 Oct, so the week that began Mon 5 Oct is held back; the next week is complete.
    assert weekly[0]["bar_time"] == to_text(datetime(2026, 10, 12, tzinfo=UTC))
