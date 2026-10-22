"""Install, remove and inspect the launchd agent that runs ``data-jobs tick``. macOS only.

The agent runs at login and then every ``every_seconds``. launchd runs an interval that came due
during sleep once the Mac wakes. Each run asks the database what is due, so the schedule itself
lives in the database and not in launchd.
"""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

LABEL = "com.asta.data-jobs.tick"
MIN_INTERVAL_SECONDS = 300


class SchedulerError(Exception):
    """The schedule could not be changed. The message is safe to show to the user."""


@dataclass(frozen=True)
class ScheduleState:
    plist_exists: bool
    loaded: bool


def plist_path(home: Optional[Path] = None) -> Path:
    return (home or Path.home()) / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def build_plist(
    *,
    python: str,
    src_dirs: Sequence[Path],
    db: Path,
    log_dir: Path,
    every_seconds: int,
    environment: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    variables = {**(environment or {}), "PYTHONPATH": os.pathsep.join(str(path) for path in src_dirs)}
    return {
        "Label": LABEL,
        "ProgramArguments": [python, "-m", "data_jobs", "--db", str(db), "tick"],
        "EnvironmentVariables": variables,
        "WorkingDirectory": str(src_dirs[0].parent),
        "StartInterval": every_seconds,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / "tick.log"),
        "StandardErrorPath": str(log_dir / "tick.err.log"),
    }


def install(
    *,
    python: str,
    src_dirs: Sequence[Path],
    db: Path,
    log_dir: Path,
    every_seconds: int,
    environment: Optional[Mapping[str, str]] = None,
    target: Optional[Path] = None,
    platform: str = sys.platform,
    run: Callable[..., Any] = subprocess.run,
    uid: Callable[[], int] = os.getuid,
) -> Path:
    _require_macos(platform)
    if every_seconds < MIN_INTERVAL_SECONDS:
        raise SchedulerError(f"The interval must be at least {MIN_INTERVAL_SECONDS // 60} minutes.")
    agent = target or plist_path()
    log_dir.mkdir(parents=True, exist_ok=True)
    agent.parent.mkdir(parents=True, exist_ok=True)
    agent.write_bytes(
        plistlib.dumps(
            build_plist(
                python=python,
                src_dirs=src_dirs,
                db=db,
                log_dir=log_dir,
                every_seconds=every_seconds,
                environment=environment,
            )
        )
    )
    domain = f"gui/{uid()}"
    # Replace any agent already loaded under this label. It is fine if none is loaded yet.
    _launchctl(run, "bootout", f"{domain}/{LABEL}")
    result = _launchctl(run, "bootstrap", domain, str(agent))
    if result.returncode != 0:
        raise SchedulerError(f"launchctl could not load the agent: {_text(result)}")
    return agent


def uninstall(
    *,
    target: Optional[Path] = None,
    platform: str = sys.platform,
    run: Callable[..., Any] = subprocess.run,
    uid: Callable[[], int] = os.getuid,
) -> bool:
    """Unload the agent and delete its file. Returns whether a file was there to delete."""
    _require_macos(platform)
    agent = target or plist_path()
    _launchctl(run, "bootout", f"gui/{uid()}/{LABEL}")
    existed = agent.exists()
    agent.unlink(missing_ok=True)
    return existed


def status(
    *,
    target: Optional[Path] = None,
    platform: str = sys.platform,
    run: Callable[..., Any] = subprocess.run,
    uid: Callable[[], int] = os.getuid,
) -> ScheduleState:
    _require_macos(platform)
    agent = target or plist_path()
    result = _launchctl(run, "print", f"gui/{uid()}/{LABEL}")
    return ScheduleState(plist_exists=agent.exists(), loaded=result.returncode == 0)


def _require_macos(platform: str) -> None:
    if platform != "darwin":
        raise SchedulerError(
            "launchd scheduling works only on macOS. Windows would use Task Scheduler, which is not set up yet."
        )


def _launchctl(run: Callable[..., Any], *args: str) -> Any:
    return run(["launchctl", *args], capture_output=True, text=True)


def _text(result: Any) -> str:
    return (result.stderr or result.stdout or "no output").strip()
