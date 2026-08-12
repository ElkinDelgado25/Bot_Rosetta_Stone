"""Tests for run execution, log/event ingestion and progress reads.

Driven with asyncio.run, matching the existing suite's style. Every manager here
gets a FakeBackend, so no test launches a browser or a container.
"""

import asyncio
import json
from collections import deque

import pytest

from rosseta_stone_script_a.presentation.web.backends import RunOutcome
from rosseta_stone_script_a.presentation.web.profiles import ProfileStore
from rosseta_stone_script_a.presentation.web.run_manager import (
    RunAlreadyActive,
    RunManager,
    RunStatus,
    _redact,
)


def _manager(tmp_path, backend):
    store = ProfileStore(tmp_path / "profiles.json")
    return store, RunManager(store, tmp_path / "state", backend=backend)


def _drain(manager, profile_id):
    """Await whichever task is carrying this profile's run."""

    async def wait():
        task = manager._tasks.get(profile_id)
        if task:
            await asyncio.gather(task, return_exceptions=True)
        if manager._worker:
            await asyncio.gather(manager._worker, return_exceptions=True)

    return wait


def test_unknown_profile_starts_idle(tmp_path, backend):
    _, manager = _manager(tmp_path, backend)
    assert manager.record_for("nope").status is RunStatus.IDLE


def test_logs_only_land_on_their_own_profile(tmp_path, backend):
    _, manager = _manager(tmp_path, backend)
    manager.ingest("desconocido", "perdido")  # no record yet
    assert manager.logs_since("desconocido", 0) == ([], 0)

    manager.record_for("p1")
    manager.ingest("p1", "primera")
    manager.ingest("p1", "segunda")

    lines, cursor = manager.logs_since("p1", 0)
    assert lines == ["primera", "segunda"]
    assert cursor == 2
    assert manager.logs_since("p1", 2) == ([], 2)


def test_two_profiles_keep_separate_logs(tmp_path, backend):
    """With parallel runs, lines must not bleed between users."""
    _, manager = _manager(tmp_path, backend)
    manager.record_for("p1")
    manager.record_for("p2")

    manager.ingest("p1", "soy uno")
    manager.ingest("p2", "soy dos")

    assert manager.logs_since("p1", 0)[0] == ["soy uno"]
    assert manager.logs_since("p2", 0)[0] == ["soy dos"]


def test_cursor_survives_buffer_overflow(tmp_path, backend):
    """A client whose cursor fell off the end gets what's left, not a crash."""
    _, manager = _manager(tmp_path, backend)
    record = manager.record_for("p1")
    record.logs = deque(maxlen=3)
    for i in range(6):
        manager.ingest("p1", f"linea-{i}")

    lines, cursor = manager.logs_since("p1", 0)
    assert lines == ["linea-3", "linea-4", "linea-5"]
    assert cursor == 6


def test_events_build_per_lesson_progress(tmp_path, backend):
    _, manager = _manager(tmp_path, backend)
    manager.record_for("p1")

    def event(ok, unit, lesson):
        return "@@EVENT " + json.dumps(
            {
                "type": "path_done",
                "ok": ok,
                "course": "SK-ENG-L1",
                "unit": unit,
                "lesson": lesson,
                "total": 5,
            }
        )

    manager.ingest("p1", event(True, 0, 0))
    manager.ingest("p1", event(True, 0, 0))
    manager.ingest("p1", event(False, 0, 1))

    record = manager.record_for("p1")
    assert record.paths_done == 2
    assert record.paths_failed == 1
    assert record.paths_total == 5

    lessons = {(l.unit, l.lesson): l for l in record.lessons.values()}
    assert lessons[(0, 0)].ok == 2
    assert lessons[(0, 1)].failed == 1

    # Events are progress, not log noise: they must not reach the console.
    assert manager.logs_since("p1", 0)[0] == []


def test_a_malformed_event_is_treated_as_a_log_line(tmp_path, backend):
    _, manager = _manager(tmp_path, backend)
    manager.record_for("p1")
    manager.ingest("p1", "@@EVENT {esto no es json")

    assert manager.logs_since("p1", 0)[0] == ["@@EVENT {esto no es json"]


def test_duplicate_run_is_rejected(tmp_path, backend):
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="U", email="u@e.com", password="x")
    backend.delay = 0.05  # keep the first run in flight

    async def scenario():
        manager.enqueue(profile.id, "x")
        with pytest.raises(RunAlreadyActive):
            manager.enqueue(profile.id, "x")
        await _drain(manager, profile.id)()

    asyncio.run(scenario())
    assert manager.record_for(profile.id).status is RunStatus.SUCCESS


def test_parallel_backend_runs_users_at_the_same_time(tmp_path, backend):
    """The whole point of the container backend: no queue."""
    store, manager = _manager(tmp_path, backend)
    backend.delay = 0.05
    uno = store.create(name="uno", email="uno@e.com", password="x")
    dos = store.create(name="dos", email="dos@e.com", password="x")

    async def scenario():
        manager.enqueue(uno.id, "x")
        manager.enqueue(dos.id, "x")
        await asyncio.sleep(0.01)  # let both tasks reach their first await
        # Neither waits for the other, and nothing sits in a queue.
        assert manager.record_for(uno.id).status is RunStatus.RUNNING
        assert manager.record_for(dos.id).status is RunStatus.RUNNING
        assert manager.queue_position(uno.id) is None
        assert manager.queue_position(dos.id) is None
        await asyncio.gather(*manager._tasks.values(), return_exceptions=True)

    asyncio.run(scenario())

    assert manager.record_for(uno.id).status is RunStatus.SUCCESS
    assert manager.record_for(dos.id).status is RunStatus.SUCCESS
    assert {call["email"] for call in backend.calls} == {"uno@e.com", "dos@e.com"}


def test_serial_backend_queues_the_second_user(tmp_path, serial_backend):
    """Without isolation there is one browser, so runs must not overlap."""
    serial_backend.delay = 0.05
    store, manager = _manager(tmp_path, serial_backend)
    uno = store.create(name="uno", email="uno@e.com", password="x")
    dos = store.create(name="dos", email="dos@e.com", password="x")

    async def scenario():
        manager.enqueue(uno.id, "x")
        manager.enqueue(dos.id, "x")
        # The worker needs a few ticks: pick from the queue, spawn the run task,
        # let it mark itself running. The backend's delay is 0.05, so this
        # lands mid-run.
        await asyncio.sleep(0.01)
        # The second user waits its turn instead of starting a second browser.
        assert manager.record_for(uno.id).status is RunStatus.RUNNING
        assert manager.record_for(dos.id).status is RunStatus.QUEUED
        assert manager.queue_position(dos.id) == 1
        await asyncio.gather(manager._worker, return_exceptions=True)

    asyncio.run(scenario())

    assert manager.record_for(uno.id).status is RunStatus.SUCCESS
    assert manager.record_for(dos.id).status is RunStatus.SUCCESS


def test_run_without_password_is_refused(tmp_path, backend):
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="U", email="u@e.com")

    with pytest.raises(ValueError):
        manager.enqueue(profile.id, None)


def test_a_failing_run_is_reported_as_error(tmp_path, backend):
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="U", email="u@e.com", password="x")
    backend.outcome = RunOutcome(ok=False, error="login roto")

    async def scenario():
        manager.enqueue(profile.id, "x")
        await _drain(manager, profile.id)()

    asyncio.run(scenario())

    record = manager.record_for(profile.id)
    assert record.status is RunStatus.ERROR
    assert record.error == "login roto"


def test_a_backend_that_explodes_is_reported_as_error(tmp_path, backend):
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="U", email="u@e.com", password="x")
    backend.raises = RuntimeError("docker no responde")

    async def scenario():
        manager.enqueue(profile.id, "x")
        await _drain(manager, profile.id)()

    asyncio.run(scenario())

    assert manager.record_for(profile.id).status is RunStatus.ERROR
    assert "docker no responde" in manager.record_for(profile.id).error


def test_a_run_harvests_what_the_form_never_asked_for(tmp_path, backend):
    """The UI only collects email and password; the run fills in the rest."""
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="u", email="u@e.com", password="x")
    backend.outcome = RunOutcome(
        ok=True,
        captured={
            "user_id": "99887",
            "user_name": "Elkin",
            "product": "fluency_builder",
            "session_token": "tok-secreto",
        },
    )

    async def scenario():
        manager.enqueue(profile.id, "x")
        await _drain(manager, profile.id)()

    asyncio.run(scenario())

    stored = store.get(profile.id)
    assert stored.last_user_id == "99887"  # names the state file
    assert stored.display_name == "Elkin"
    assert stored.product == "fluency_builder"
    assert manager.sessions.load(profile.id)["session_token"] == "tok-secreto"


def test_verify_mode_reaches_the_backend_and_sends_nothing(tmp_path, backend):
    """Verificar inicia sesión y detecta el producto, sin enviar progreso."""
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="u", email="u@e.com", password="x")
    backend.outcome = RunOutcome(
        ok=True,
        captured={
            "user_id": "42",
            "product": "foundations",
            "institution_selected": True,
        },
    )

    async def scenario():
        manager.enqueue(profile.id, "x", mode="verify")
        await _drain(manager, profile.id)()

    asyncio.run(scenario())

    assert backend.calls[0]["mode"] == "verify"
    record = manager.record_for(profile.id)
    assert record.status is RunStatus.SUCCESS
    assert record.mode == "verify"
    assert record.paths_done == 0  # nada enviado

    stored = store.get(profile.id)
    assert stored.product == "foundations"
    assert stored.institution_selected is True


def test_a_login_without_the_institutional_step_records_false(tmp_path, backend):
    """False es una respuesta real: no debe confundirse con 'sin verificar'."""
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="u", email="u@e.com", password="x")
    assert store.get(profile.id).institution_selected is None

    backend.outcome = RunOutcome(
        ok=True, captured={"product": "fluency_builder", "institution_selected": False}
    )

    async def scenario():
        manager.enqueue(profile.id, "x", mode="verify")
        await _drain(manager, profile.id)()

    asyncio.run(scenario())

    assert store.get(profile.id).institution_selected is False


def test_run_mode_is_the_default(tmp_path, backend):
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="u", email="u@e.com", password="x")

    async def scenario():
        manager.enqueue(profile.id, "x")
        await _drain(manager, profile.id)()

    asyncio.run(scenario())
    assert backend.calls[0]["mode"] == "run"


def test_a_run_that_captures_nothing_leaves_the_profile_alone(tmp_path, backend):
    """user_name is optional upstream: a missing one must not blank the field."""
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="u", email="u@e.com", password="x")
    store.update(profile.id, display_name="Nombre previo")
    backend.outcome = RunOutcome(ok=True, captured={"user_id": "99887"})

    async def scenario():
        manager.enqueue(profile.id, "x")
        await _drain(manager, profile.id)()

    asyncio.run(scenario())

    assert store.get(profile.id).display_name == "Nombre previo"


def test_tokens_are_stored_per_user(tmp_path, backend):
    store, manager = _manager(tmp_path, backend)
    uno = store.create(name="uno", email="uno@e.com", password="x")
    dos = store.create(name="dos", email="dos@e.com", password="x")

    async def scenario():
        backend.outcome = RunOutcome(ok=True, captured={"session_token": "tok-uno"})
        manager.enqueue(uno.id, "x")
        await _drain(manager, uno.id)()
        backend.outcome = RunOutcome(ok=True, captured={"session_token": "tok-dos"})
        manager.enqueue(dos.id, "x")
        await _drain(manager, dos.id)()

    asyncio.run(scenario())

    assert manager.sessions.load(uno.id)["session_token"] == "tok-uno"
    assert manager.sessions.load(dos.id)["session_token"] == "tok-dos"


def test_progress_reads_the_state_file(tmp_path, backend):
    store, manager = _manager(tmp_path, backend)
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


def test_progress_counts_fluency_accounts_too(tmp_path, backend):
    """A Fluency account writes fluency_<user_id>.json, not <user_id>.json."""
    store, manager = _manager(tmp_path, backend)
    profile = store.create(name="U", email="u@e.com", password="x")
    store.update(profile.id, last_user_id="777", product="fluency_builder")

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "fluency_777.json").write_text(
        json.dumps(
            {
                "completed_path_keys": ["a", "b", "c", "d"],
                "run_log": [{"date": "1999-01-01", "count": 4}],
                "last_run": "1999-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    progress = manager.progress_for(store.get(profile.id))
    assert progress["total_done"] == 4  # was 0 before: only Foundations counted
    assert progress["last_run"] == "1999-01-01T00:00:00Z"


def test_events_with_named_lessons_do_not_break_ingestion(tmp_path, backend):
    """Fluency names its lessons; coercing them to int used to raise."""
    _, manager = _manager(tmp_path, backend)
    manager.record_for("p1")

    manager.ingest(
        "p1",
        "@@EVENT "
        + json.dumps(
            {
                "type": "path_done",
                "ok": True,
                "course": "Speak with Pilots (B1)",
                "unit": None,
                "lesson": "Preflight",
                "path_type": "test-cloze-dropdowns",
            }
        ),
    )

    record = manager.record_for("p1")
    assert record.paths_done == 1
    lesson = list(record.lessons.values())[0]
    assert lesson.lesson == "Preflight"
    assert lesson.unit is None


def test_progress_without_a_state_file_is_zero(tmp_path, backend):
    store, manager = _manager(tmp_path, backend)
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
