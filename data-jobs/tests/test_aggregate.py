from datetime import date, datetime, timezone

import pytest

from data_jobs.aggregate import QUARTERLY, WEEKLY, MONTHLY, aggregate, next_period_start, period_start
from data_jobs.store import Bar

UTC = timezone.utc


def day_bar(day, *, o, h, l, c, v=None, month=10):
    return Bar(
        bar_time=datetime(2026, month, day, tzinfo=UTC),
        open=o,
        high=h,
        low=l,
        close=c,
        volume=v,
        is_closed=True,
    )


WEEK_OF_19_OCT = [
    day_bar(19, o=100, h=105, l=99, c=102, v=10),
    day_bar(20, o=102, h=110, l=101, c=108, v=20),
    day_bar(21, o=108, h=109, l=104, c=105, v=30),
    day_bar(22, o=105, h=107, l=98, c=99, v=40),
    day_bar(23, o=99, h=103, l=97, c=101, v=50),
]


def test_a_week_takes_first_open_highest_high_lowest_low_last_close_and_summed_volume():
    weekly = aggregate(WEEK_OF_19_OCT, WEEKLY, now=datetime(2026, 10, 26, tzinfo=UTC))

    assert len(weekly) == 1
    bar = weekly[0]
    assert bar.bar_time == datetime(2026, 10, 19, tzinfo=UTC)
    assert (bar.open, bar.high, bar.low, bar.close) == (100, 110, 97, 101)
    assert bar.volume == 150
    assert bar.is_closed is True


def test_the_current_week_is_still_forming_until_the_next_week_starts():
    weekly = aggregate(WEEK_OF_19_OCT, WEEKLY, now=datetime(2026, 10, 22, 12, tzinfo=UTC))

    assert weekly[0].is_closed is False


def test_a_holiday_that_removes_the_first_day_keeps_the_weekly_key_on_monday():
    holiday_week = [
        day_bar(13, o=50, h=55, l=49, c=52, v=5),
        day_bar(14, o=52, h=56, l=51, c=54, v=5),
        day_bar(15, o=54, h=57, l=53, c=56, v=5),
    ]

    weekly = aggregate(holiday_week, WEEKLY, now=datetime(2026, 10, 30, tzinfo=UTC))

    assert weekly[0].bar_time == datetime(2026, 10, 12, tzinfo=UTC)
    assert weekly[0].open == 50
    assert weekly[0].close == 56


def test_a_month_and_a_quarter_group_the_same_way_on_their_first_day():
    october = aggregate(WEEK_OF_19_OCT, MONTHLY, now=datetime(2026, 10, 22, tzinfo=UTC))
    assert october[0].bar_time == datetime(2026, 10, 1, tzinfo=UTC)
    assert october[0].is_closed is False

    quarter = aggregate(
        [
            day_bar(1, month=7, o=10, h=12, l=9, c=11, v=1),
            day_bar(30, month=9, o=20, h=25, l=18, c=24, v=2),
        ],
        QUARTERLY,
        now=datetime(2026, 10, 1, tzinfo=UTC),
    )
    assert len(quarter) == 1
    assert quarter[0].bar_time == datetime(2026, 7, 1, tzinfo=UTC)
    assert (quarter[0].open, quarter[0].high, quarter[0].low, quarter[0].close) == (10, 25, 9, 24)
    assert quarter[0].is_closed is True


def test_volume_is_left_blank_when_any_day_has_none():
    bars = [day_bar(19, o=1, h=2, l=1, c=2, v=10), day_bar(20, o=2, h=3, l=2, c=3, v=None)]

    weekly = aggregate(bars, WEEKLY, now=datetime(2026, 10, 26, tzinfo=UTC))

    assert weekly[0].volume is None


def test_two_bars_on_the_same_day_are_rejected():
    with pytest.raises(ValueError, match="one bar per day"):
        aggregate(
            [day_bar(19, o=1, h=2, l=1, c=2), day_bar(19, o=1, h=3, l=1, c=3)],
            WEEKLY,
            now=datetime(2026, 10, 26, tzinfo=UTC),
        )


def test_an_unknown_period_is_rejected():
    with pytest.raises(ValueError, match="Unsupported period"):
        aggregate(WEEK_OF_19_OCT, "4H", now=datetime(2026, 10, 26, tzinfo=UTC))


def test_period_boundaries_for_weeks_months_and_quarters():
    assert period_start(date(2026, 10, 25), WEEKLY) == date(2026, 10, 19)  # Sunday belongs to the Monday's week
    assert period_start(date(2026, 11, 5), MONTHLY) == date(2026, 11, 1)
    assert period_start(date(2026, 11, 5), QUARTERLY) == date(2026, 10, 1)
    assert next_period_start(date(2026, 12, 1), MONTHLY) == date(2027, 1, 1)
    assert next_period_start(date(2026, 10, 1), QUARTERLY) == date(2027, 1, 1)
