from datetime import timedelta

from data_jobs.runner import FAILED, MAX_RUNS_PER_PERIOD, PARTIAL, SUCCEEDED, JobSpec, job_status, run_job, tick
from data_jobs.store import connect
from support import NOW, FakeFetcher, FixedClock

SPEC = JobSpec(
    name="gm-daily",
    interval=timedelta(days=1),
    symbols=("A", "B", "C"),
    timeframes=("1D",),
    bar_count=2,
)


class Flaky(FakeFetcher):
    """Fails each (symbol, timeframe) the first ``fail_times`` attempts, then succeeds."""

    def __init__(self, fail_times):
        super().__init__()
        self.fail_times = dict(fail_times)
        self.attempts = {}

    def fetch(self, symbol, timeframe, *, count):
        key = (symbol, timeframe)
        self.attempts[key] = self.attempts.get(key, 0) + 1
        if self.attempts[key] <= self.fail_times.get(key, 0):
            self.calls.append((symbol, timeframe, count))
            raise ConnectionError("chart did not load in time")
        return super().fetch(symbol, timeframe, count=count)


def _symbols_fetched(fetcher, since):
    return [symbol for symbol, _, _ in fetcher.calls[since:]]


def test_a_transient_failure_is_retried_once_within_the_same_run():
    conn = connect(":memory:")
    fetcher = Flaky({("B", "1D"): 1})

    result = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))

    assert result.status == SUCCEEDED
    assert result.items_failed == 0
    assert _symbols_fetched(fetcher, 0) == ["A", "B", "C", "B"]  # the retry follows the first pass


def test_a_partial_run_is_retried_an_hour_later_for_its_failed_symbol_only():
    conn = connect(":memory:")
    fetcher = Flaky({("B", "1D"): 2})  # fails in the run and in its immediate retry, then recovers

    first = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))
    assert first.status == PARTIAL
    assert first.items_failed == 1

    mark = len(fetcher.calls)
    later = NOW + timedelta(hours=1)
    results = tick(conn, [SPEC], fetcher, clock=FixedClock(later))

    assert [result.status for result in results] == [SUCCEEDED]
    assert _symbols_fetched(fetcher, mark) == ["B"]  # only the failed symbol is fetched again
    status = job_status(conn, now=later)[0]
    assert status.progress.total == 1
    assert status.progress.failed == 0
    assert status.next_run_at == "2026-10-23T13:00:00.000000Z"  # a day after this run, the normal interval


def test_the_retries_stop_after_the_cap_and_the_job_waits_for_its_normal_interval():
    conn = connect(":memory:")
    fetcher = Flaky({("B", "1D"): 999})  # never recovers
    clock = FixedClock(NOW)

    run_job(conn, SPEC, fetcher, clock=clock)
    for _ in range(MAX_RUNS_PER_PERIOD - 1):
        clock.now += timedelta(hours=1)
        tick(conn, [SPEC], fetcher, clock=clock)

    runs = conn.execute("SELECT COUNT(*) AS n FROM job_runs WHERE job_name = 'gm-daily'").fetchone()["n"]
    assert runs == MAX_RUNS_PER_PERIOD
    status = job_status(conn, now=clock.now)[0]
    # The last retry only contains the failed symbol, so it fails as a whole.
    assert status.latest_status == FAILED
    assert status.next_run_at == "2026-10-23T15:00:00.000000Z"  # one day after the last run, not an hour

    clock.now += timedelta(hours=1)
    assert tick(conn, [SPEC], fetcher, clock=clock) == []


def test_a_new_day_retries_the_full_job_rather_than_yesterdays_failures():
    conn = connect(":memory:")
    fetcher = Flaky({("B", "1D"): 2})
    run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))

    tomorrow = NOW + timedelta(days=1)
    mark = len(fetcher.calls)
    tick(conn, [SPEC], fetcher, clock=FixedClock(tomorrow))

    assert _symbols_fetched(fetcher, mark) == ["A", "B", "C"]


def test_a_run_where_everything_fails_is_retried_for_everything_an_hour_later():
    conn = connect(":memory:")
    fetcher = Flaky({("A", "1D"): 999, ("B", "1D"): 999, ("C", "1D"): 999})

    result = run_job(conn, SPEC, fetcher, clock=FixedClock(NOW))
    assert result.status == FAILED

    mark = len(fetcher.calls)
    tick(conn, [SPEC], fetcher, clock=FixedClock(NOW + timedelta(hours=1)))
    # The retry run fetches everything, then its own immediate retry fetches the failures again.
    assert _symbols_fetched(fetcher, mark) == ["A", "B", "C", "A", "B", "C"]
