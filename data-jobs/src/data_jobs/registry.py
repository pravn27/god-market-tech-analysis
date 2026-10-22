"""Jobs that the scheduled run executes.

Empty until a bar source exists. When the Global Market fetcher is built, its job specs and
fetcher are returned from here, and both the command line and the scheduled run pick them up.
"""

from typing import Optional, Tuple

from .runner import BarFetcher, JobSpec


def registered_jobs() -> Tuple[JobSpec, ...]:
    return ()


def bar_source() -> Optional[BarFetcher]:
    return None
