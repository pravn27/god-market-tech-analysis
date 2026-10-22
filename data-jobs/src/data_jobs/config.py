"""Absolute locations, so the scheduled run finds the same database and code whatever its working directory."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent  # .../data-jobs/src/data_jobs
SRC_DIR = PACKAGE_DIR.parent  # .../data-jobs/src
PROJECT_DIR = PACKAGE_DIR.parents[1]  # .../data-jobs
# The live app's package. The Desktop fallback reuses its chart reader, so jobs need it on the path.
GOD_MARKET_SRC_DIR = PROJECT_DIR.parent / "src"
# The live app's local settings file (gitignored). Read only for the Desktop bridge settings.
ENV_FILE = GOD_MARKET_SRC_DIR.parent / ".env.local"
DEFAULT_DB = PROJECT_DIR / "data" / "jobs.sqlite3"
LOG_DIR = Path.home() / "Library" / "Logs" / "data-jobs"
