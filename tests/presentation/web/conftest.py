"""Shared guards for the web-layer tests.

A run drives a real browser (in-process) or starts a real container (docker).
No test may do either, so every test here gets a FakeBackend injected. Nothing
in this package resolves a backend on its own: ``RunManager`` and ``create_app``
both take one, and the tests always pass it.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from Resolucion_script_rosseta.presentacion.web.backends import RunOutcome


class FakeBackend:
    """Stands in for a real backend. Records calls, never launches anything."""

    name = "fake"

    def __init__(self, supports_parallel: bool = True) -> None:
        self.supports_parallel = supports_parallel
        self.calls: list[dict[str, Any]] = []
        self.cancelled: list[str] = []
        self.delay: float = 0.0
        self.outcome: RunOutcome | None = None
        self.raises: Exception | None = None
        self.lines: list[str] = []

    async def run(self, profile, password, sink, mode: str = "run") -> RunOutcome:
        self.calls.append(
            {"profile_id": profile.id, "email": profile.email, "mode": mode}
        )
        for line in self.lines:
            sink(line)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raises:
            raise self.raises
        return self.outcome or RunOutcome(ok=True, captured={})

    async def cancel(self, profile_id: str) -> bool:
        self.cancelled.append(profile_id)
        return True


@pytest.fixture
def backend() -> FakeBackend:
    """A backend that isolates runs, so they can overlap (the Docker case)."""
    return FakeBackend(supports_parallel=True)


@pytest.fixture
def serial_backend() -> FakeBackend:
    """A backend without isolation, where runs must queue (the local case)."""
    return FakeBackend(supports_parallel=False)

