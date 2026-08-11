"""Tests for the run queue, log buffering and progress reads.

Driven with asyncio.run, matching the existing suite's style. No test here
launches a browser: the queue is exercised with a profile that was deleted, so
the worker resolves it to an error before any run starts.
"""

import asyncio
import json
from collections import deque

import pytest

from rosseta_stone_script_a.presentation.web.profiles import ProfileStore
from rosseta_stone_script_a.presentation.web.run_manager import (
    RunAlreadyActive,
    RunManager,
    RunStatus,
    _redact,
)


def _manager(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    return store, RunManager(store, tmp_path / "state")


def test_unknown_profile_starts_idle(tmp_path):
    _, manager = _manager(tmp_path)
    assert manager.record_for("nope").status is RunStatus.IDLE


def test_logs_only_land_on_the_active_profile(tmp_path):
    _, manager = _manager(tmp_path)
    manager._append_log("perdido")  # no active run
    assert manager.logs_since("cualquiera", 0) == ([], 0)

    manager.record_for("p1")
    manager._active_profile_id = "p1"
    manager._append_log("primera")
    manager._append_log("segunda")

    lines, cursor = manager.logs_since("p1", 0)
    assert lines == ["primera", "segunda"]
    assert cursor == 2
    assert manager.logs_since("p1", 2) == ([], 2)


def test_cursor_survives_buffer_overflow(tmp_path):
    """A client whose cursor fell off the end gets what's left, not a crash."""
    _, manager = _manager(tmp_path)
    record = manager.record_for("p1")
    record.logs = deque(maxlen=3)
    manager._active_profile_id = "p1"
    for i in range(6):
        manager._append_log(f"linea-{i}")

    lines, cursor = manager.logs_since("p1", 0)
    assert lines == ["linea-3", "linea-4", "linea-5"]
    assert cursor == 6


def test_duplicate_enqueue_is_rejected(tmp_path, no_real_browser):
    store, manager = _manager(tmp_path)
    profile = store.create(name="U", email="u@e.com", password="x")
    no_real_browser.delay = 0.05  # keep the first run in flight

    async def scenario():
        manager.enqueue(profile.id, "x")
        with pytest.raises(RunAlreadyActive):
            manager.enqueue(profile.id, "x")
        await manager._worker

    asyncio.run(scenario())
    assert manager.record_for(profile.id).status is RunStatus.SUCCESS


def test_successful_run_stores_the_captured_user_id(tmp_path, no_real_browser):
    """The tracking user_id names the state file, so it must be remembered."""
    store, manager = _manager(tmp_path)
    profile = store.create(name="U", email="u@e.com", password="x")
    no_real_browser.captured = {"user_id": "99887"}

    async def scenario():
        manager.enqueue(profile.id, "x")
        await manager._worker

    asyncio.run(scenario())

    assert store.get(profile.id).last_user_id == "99887"
    assert no_real_browser.calls[0]["headless"] is True


def test_a_failing_run_is_reported_as_error(tmp_path, no_real_browser):
    store, manager = _manager(tmp_path)
    profile = store.create(name="U", email="u@e.com", password="x")
    no_real_browser.raises = RuntimeError("login roto")

    async def scenario():
        manager.enqueue(profile.id, "x")
        await manager._worker

    asyncio.run(scenario())

    record = manager.record_for(profile.id)
    assert record.status is RunStatus.ERROR
    assert record.error == "login roto"


def test_queue_drains_and_releases_the_worker(tmp_path):
    """A deleted profile fails its run, and the queue keeps accepting work."""
    store, manager = _manager(tmp_path)
    profile = store.create(name="U", email="u@e.com", password="x")
    store.delete(profile.id)

    async def scenario():
        manager.enqueue(profile.id, "x")
        await manager._worker
        assert manager._worker_running is False
        # The flag was released, so a second enqueue starts a fresh worker.
        manager.enqueue(profile.id, "x")
        await manager._worker

    asyncio.run(scenario())

    record = manager.record_for(profile.id)
    assert record.status is RunStatus.ERROR
    assert "ya no existe" in record.error


def test_run_without_password_fails_before_launching(tmp_path):
    store, manager = _manager(tmp_path)
    profile = store.create(name="U", email="u@e.com")  # no password stored

    async def scenario():
        manager.enqueue(profile.id, None)
        await manager._worker

    asyncio.run(scenario())

    record = manager.record_for(profile.id)
    assert record.status is RunStatus.ERROR
    assert "contraseña" in record.error


def test_progress_reads_the_state_file(tmp_path):
    store, manager = _manager(tmp_path)
    profile = store.create(name="U", email="u@e.com", password="x")
    store.update(profile.id, last_user_id="12345")

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "12345.json").write_text(
        json.dumps(
            {
                "completed_path_keys": ["a", "b", "c"],
                "run_log": [{"date": "1999-01-01", "count": 3}],
                "last_run": "1999-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    progress = manager.progress_for(store.get(profile.id))
    assert progress["total_done"] == 3
    assert progress["done_today"] == 0  # the run_log entry is not today
    assert progress["last_run"] == "1999-01-01T00:00:00Z"


def test_progress_without_a_state_file_is_zero(tmp_path):
    store, manager = _manager(tmp_path)
    profile = store.create(name="U", email="u@e.com")
    assert manager.progress_for(profile) == {
        "total_done": 0,
        "done_today": 0,
        "last_run": None,
    }


def test_redaction_strips_tokens_from_log_lines():
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abcdefghij"
    assert jwt not in _redact(f"authorization: {jwt}")
    assert "<jwt-redacted>" in _redact(f"authorization: {jwt}")
    assert "abc123def456" not in _redact('session_token: "abc123def456"')
    assert "hunter2" not in _redact("password=hunter2")
