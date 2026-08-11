"""Shared guards for the web-layer tests.

The run manager's job is to call ``RosettaCLI.enter_rosetta``, which launches a
real browser and logs in to Rosetta Stone. No test may do that, so the CLI is
replaced for every test in this package. Anything that would have started a run
records the call instead.
"""

import asyncio

import pytest

from rosseta_stone_script_a.presentation.web import run_manager as run_manager_module


class FakeCLI:
    """Stands in for RosettaCLI. Records calls, never opens a browser."""

    calls: list[dict] = []
    delay: float = 0.0
    raises: Exception | None = None
    captured: dict | None = None

    async def enter_rosetta(self, **kwargs):
        type(self).calls.append(kwargs)
        if type(self).delay:
            await asyncio.sleep(type(self).delay)
        if type(self).raises:
            raise type(self).raises
        return type(self).captured or {}


@pytest.fixture(autouse=True)
def no_real_browser(monkeypatch):
    """Point the run manager at FakeCLI for the duration of each test."""
    FakeCLI.calls = []
    FakeCLI.delay = 0.0
    FakeCLI.raises = None
    FakeCLI.captured = None
    monkeypatch.setattr(run_manager_module, "RosettaCLI", FakeCLI)
    return FakeCLI
