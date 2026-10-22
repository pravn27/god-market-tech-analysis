import asyncio

import pytest

from god_market_api.desktop_chart_lock import ChartBusyError, desktop_chart_lock


def test_a_second_holder_waits_and_then_reports_the_chart_busy(tmp_path):
    path = tmp_path / "chart.lock"

    async def scenario() -> None:
        async with desktop_chart_lock(path, timeout=1.0):
            with pytest.raises(ChartBusyError, match="in use"):
                async with desktop_chart_lock(path, timeout=0.3):
                    pass

    asyncio.run(scenario())


def test_the_lock_is_released_when_the_holder_leaves(tmp_path):
    path = tmp_path / "chart.lock"

    async def scenario() -> str:
        async with desktop_chart_lock(path, timeout=1.0):
            pass
        async with desktop_chart_lock(path, timeout=0.3):
            return "acquired"

    assert asyncio.run(scenario()) == "acquired"


def test_the_lock_is_released_even_when_the_holder_fails(tmp_path):
    path = tmp_path / "chart.lock"

    async def scenario() -> str:
        with pytest.raises(RuntimeError):
            async with desktop_chart_lock(path, timeout=1.0):
                raise RuntimeError("chart read failed")
        async with desktop_chart_lock(path, timeout=0.3):
            return "acquired"

    assert asyncio.run(scenario()) == "acquired"


def test_the_lock_file_and_its_folder_are_created(tmp_path):
    path = tmp_path / "nested" / "chart.lock"

    async def scenario() -> None:
        async with desktop_chart_lock(path, timeout=1.0):
            pass

    asyncio.run(scenario())
    assert path.exists()
