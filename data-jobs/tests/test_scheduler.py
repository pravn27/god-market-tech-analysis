import plistlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_jobs import scheduler
from data_jobs.scheduler import LABEL, SchedulerError, build_plist, install, status, uninstall


class FakeLaunchctl:
    """Records launchctl calls and answers with the return codes it is given."""

    def __init__(self, *, bootstrap_code: int = 0, bootstrap_error: str = "", print_code: int = 0):
        self.calls = []
        self.bootstrap_code = bootstrap_code
        self.bootstrap_error = bootstrap_error
        self.print_code = print_code

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        if argv[1] == "bootstrap":
            return SimpleNamespace(returncode=self.bootstrap_code, stdout="", stderr=self.bootstrap_error)
        if argv[1] == "print":
            return SimpleNamespace(returncode=self.print_code, stdout="", stderr="")
        return SimpleNamespace(returncode=113, stdout="", stderr="Could not find service")


def _install(tmp_path, run, **overrides):
    options = dict(
        python="/venv/bin/python",
        src_dirs=(Path("/repo/data-jobs/src"), Path("/repo/src")),
        db=Path("/repo/data-jobs/data/jobs.sqlite3"),
        log_dir=tmp_path / "logs",
        every_seconds=3600,
        target=tmp_path / "LaunchAgents" / f"{LABEL}.plist",
        platform="darwin",
        run=run,
        uid=lambda: 501,
    )
    options.update(overrides)
    return install(**options)


def test_the_agent_runs_tick_on_the_interval_and_at_load_with_absolute_paths(tmp_path):
    plist = build_plist(
        python="/venv/bin/python",
        src_dirs=(Path("/repo/data-jobs/src"), Path("/repo/src")),
        db=Path("/repo/data-jobs/data/jobs.sqlite3"),
        log_dir=tmp_path,
        every_seconds=3600,
    )

    assert plist["Label"] == LABEL
    assert plist["ProgramArguments"] == [
        "/venv/bin/python",
        "-m",
        "data_jobs",
        "--db",
        "/repo/data-jobs/data/jobs.sqlite3",
        "tick",
    ]
    assert plist["EnvironmentVariables"] == {"PYTHONPATH": "/repo/data-jobs/src:/repo/src"}
    assert plist["StartInterval"] == 3600
    assert plist["RunAtLoad"] is True
    assert plist["StandardOutPath"] == str(tmp_path / "tick.log")


def test_install_writes_the_agent_file_and_loads_it_under_the_user_session(tmp_path):
    fake = FakeLaunchctl()

    agent = _install(tmp_path, fake)

    written = plistlib.loads(agent.read_bytes())
    assert written["Label"] == LABEL
    assert fake.calls == [
        ["launchctl", "bootout", f"gui/501/{LABEL}"],
        ["launchctl", "bootstrap", "gui/501", str(agent)],
    ]


def test_install_reports_launchctl_failures(tmp_path):
    fake = FakeLaunchctl(bootstrap_code=5, bootstrap_error="Bootstrap failed: 5")

    with pytest.raises(SchedulerError, match="Bootstrap failed: 5"):
        _install(tmp_path, fake)


def test_install_refuses_intervals_under_five_minutes(tmp_path):
    with pytest.raises(SchedulerError, match="at least 5 minutes"):
        _install(tmp_path, FakeLaunchctl(), every_seconds=60)


def test_install_refuses_to_run_off_macos(tmp_path):
    with pytest.raises(SchedulerError, match="only on macOS"):
        _install(tmp_path, FakeLaunchctl(), platform="win32")


def test_uninstall_unloads_and_removes_the_file(tmp_path):
    fake = FakeLaunchctl()
    agent = _install(tmp_path, fake)

    existed = uninstall(target=agent, platform="darwin", run=fake, uid=lambda: 501)

    assert existed is True
    assert not agent.exists()
    assert fake.calls[-1] == ["launchctl", "bootout", f"gui/501/{LABEL}"]


def test_uninstall_is_quiet_when_nothing_is_installed(tmp_path):
    fake = FakeLaunchctl()

    existed = uninstall(target=tmp_path / "missing.plist", platform="darwin", run=fake, uid=lambda: 501)

    assert existed is False


def test_status_reports_whether_the_agent_is_loaded(tmp_path):
    fake = FakeLaunchctl(print_code=0)
    agent = _install(tmp_path, fake)

    state = status(target=agent, platform="darwin", run=fake, uid=lambda: 501)

    assert state.plist_exists is True
    assert state.loaded is True

    not_loaded = status(target=agent, platform="darwin", run=FakeLaunchctl(print_code=113), uid=lambda: 501)
    assert not_loaded.loaded is False


def test_the_default_agent_location_is_in_the_user_launch_agents_folder(tmp_path):
    path = scheduler.plist_path(home=tmp_path)

    assert path == tmp_path / "Library" / "LaunchAgents" / f"{LABEL}.plist"
