"""Per-profile run execution, one container per user.

With the Docker backend every user runs at once, each in its own throwaway
container, and its stdout is streamed straight into that user's log buffer. With
the in-process fallback there is no isolation — one browser, one state file — so
runs are queued and taken one at a time.

Two channels come back from a run:

* plain log lines, shown in the live console;
* structured events (``shared.events``), which drive the per-lesson progress.

Persisted progress is still read from ``RunProgressState`` on disk rather than
kept in memory: ``complete_foundations`` saves after every accepted POST, so the
file is accurate mid-run and survives a restart.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from threading import Lock
from typing import Any

from rosseta_stone_script_a.infrastructure.core import get_settings
from rosseta_stone_script_a.infrastructure.state.state_store import StateStore
from rosseta_stone_script_a.shared import events

from .backends import InProcessBackend, RunOutcome, select_backend
from .profiles import Profile, ProfileStore
from .session_store import SessionStore

MAX_LOG_LINES = 2000
MAX_LESSONS_TRACKED = 200

# Session tokens and JWTs travel through debug logs. The browser is a wider
# audience than a local log file, so scrub them on the way out.
_REDACTIONS = (
    re.compile(r"eyJ[A-Za-z0-9_\-\.]{20,}"),
    re.compile(r"(?i)(session[_-]?token[\"'\s:=]+)([A-Za-z0-9_\-]{8,})"),
    re.compile(r"(?i)(password[\"'\s:=]+)(\S+)"),
)


def _redact(message: str) -> str:
    message = _REDACTIONS[0].sub("<jwt-redacted>", message)
    message = _REDACTIONS[1].sub(r"\1<redacted>", message)
    message = _REDACTIONS[2].sub(r"\1<redacted>", message)
    return message


class RunStatus(str, Enum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class LessonProgress:
    """Per-lesson tally, built from path_done events."""

    course: str
    # Foundations gives integers, Fluency gives a title (and no unit at all).
    unit: Any
    lesson: Any
    ok: int = 0
    failed: int = 0

    @property
    def key(self) -> str:
        return f"{self.course}|{self.unit}|{self.lesson}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "course": self.course,
            "unit": self.unit,
            "lesson": self.lesson,
            "ok": self.ok,
            "failed": self.failed,
        }


@dataclass
class RunRecord:
    """The latest (or in-flight) run for one profile."""

    profile_id: str
    status: RunStatus = RunStatus.IDLE
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    total_lines: int = 0
    lessons: dict[str, LessonProgress] = field(default_factory=dict)
    paths_done: int = 0
    paths_failed: int = 0
    paths_total: int | None = None
    # "run" sends progress; "verify" only logs in and reports what it found.
    mode: str = "run"

    def public_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "status": self.status.value,
            "mode": self.mode,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "total_lines": self.total_lines,
            "paths_done": self.paths_done,
            "paths_failed": self.paths_failed,
            "paths_total": self.paths_total,
            "lessons": [lesson.as_dict() for lesson in self.lessons.values()],
        }

    def reset_for_new_run(self) -> None:
        self.logs.clear()
        self.total_lines = 0
        self.lessons.clear()
        self.paths_done = 0
        self.paths_failed = 0
        self.paths_total = None
        self.error = None
        self.finished_at = None


class _RunLogHandler(logging.Handler):
    """Feeds root-logger records into the active run's buffer.

    Only meaningful for the in-process backend, where the run shares this
    process. Container runs get their lines from the container's stdout.
    """

    def __init__(self, manager: "RunManager") -> None:
        super().__init__(level=logging.INFO)
        self._manager = manager

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a broken log must not kill a run
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self._manager.ingest_in_process(f"{stamp} {record.levelname:<7} {message}")


class RunManager:
    """Owns the running set, each profile's log buffer and its last result."""

    def __init__(
        self,
        store: ProfileStore,
        state_dir: Path,
        backend: Any | None = None,
        login_url: str | None = None,
    ) -> None:
        self._store = store
        self._state_dir = state_dir
        self.sessions = SessionStore(state_dir)
        self._records: dict[str, RunRecord] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._queue: deque[tuple[str, str, str]] = deque()
        self._lock = Lock()
        self._handler = _RunLogHandler(self)
        self._handler_attached = False
        self._worker: asyncio.Task | None = None
        self._worker_running = False
        self._in_process_profile: str | None = None

        if backend is None:
            url = login_url or get_settings().rosseta_settings.rosetta_login_url
            backend = select_backend(state_dir, url)
        self.backend = backend

    @property
    def backend_name(self) -> str:
        return getattr(self.backend, "name", "desconocido")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        if not self._handler_attached:
            logging.getLogger().addHandler(self._handler)
            self._handler_attached = True

    async def shutdown(self) -> None:
        logging.getLogger().removeHandler(self._handler)
        self._handler_attached = False
        for task in list(self._tasks.values()):
            if not task.done():
                task.cancel()
        if self._worker and not self._worker.done():
            self._worker.cancel()

    # ------------------------------------------------------------------
    # Launching
    # ------------------------------------------------------------------

    def enqueue(
        self, profile_id: str, password: str | None = None, mode: str = "run"
    ) -> RunRecord:
        """Start a run for *profile_id*, or queue it if runs can't overlap.

        ``mode="verify"`` logs in, walks the institutional step and detects the
        product, then stops without sending anything.
        """
        if not password:
            raise ValueError("Se requiere una contraseña para ejecutar")

        parallel = getattr(self.backend, "supports_parallel", False)
        with self._lock:
            record = self._records.get(profile_id)
            if record and record.status in (RunStatus.RUNNING, RunStatus.QUEUED):
                raise RunAlreadyActive(profile_id)

            record = self._records.setdefault(profile_id, RunRecord(profile_id))
            record.reset_for_new_run()
            record.status = RunStatus.QUEUED
            record.started_at = _now()
            record.mode = mode

            if not parallel:
                self._queue.append((profile_id, password, mode))
                needs_worker = not self._worker_running
                if needs_worker:
                    self._worker_running = True

        self.start()
        if parallel:
            self._tasks[profile_id] = asyncio.create_task(
                self._execute(profile_id, password, mode)
            )
        elif needs_worker:
            self._worker = asyncio.create_task(self._drain_queue())
        return record

    async def _drain_queue(self) -> None:
        """One-at-a-time execution, for the backend without isolation."""
        try:
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    profile_id, password, mode = self._queue.popleft()
                task = asyncio.create_task(self._execute(profile_id, password, mode))
                self._tasks[profile_id] = task
                try:
                    await task
                except asyncio.CancelledError:
                    self._finish(profile_id, RunStatus.CANCELLED, "Detenido por el usuario")
                finally:
                    self._tasks.pop(profile_id, None)
        finally:
            with self._lock:
                self._worker_running = False

    async def _execute(
        self, profile_id: str, password: str, mode: str = "run"
    ) -> None:
        profile = self._store.get(profile_id)
        if profile is None:
            self._finish(profile_id, RunStatus.ERROR, "El perfil ya no existe")
            return

        with self._lock:
            record = self._records.setdefault(profile_id, RunRecord(profile_id))
            record.status = RunStatus.RUNNING
            self._in_process_profile = (
                profile_id
                if isinstance(self.backend, InProcessBackend)
                else self._in_process_profile
            )

        def sink(line: str) -> None:
            self.ingest(profile_id, line)

        try:
            outcome: RunOutcome = await self.backend.run(
                profile, password, sink, mode
            )
        except asyncio.CancelledError:
            self._finish(profile_id, RunStatus.CANCELLED, "Detenido por el usuario")
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI
            self._finish(profile_id, RunStatus.ERROR, str(exc) or exc.__class__.__name__)
            return
        finally:
            self._tasks.pop(profile_id, None)
            with self._lock:
                if self._in_process_profile == profile_id:
                    self._in_process_profile = None

        if not outcome.ok:
            self._finish(profile_id, RunStatus.ERROR, outcome.error)
            return

        self._absorb_captured(profile, outcome.captured)
        self._finish(profile_id, RunStatus.SUCCESS, None)

    def _absorb_captured(self, profile: Profile, captured: dict[str, Any]) -> None:
        """Keep what the session already knows instead of asking the user."""
        captured = captured or {}
        self.sessions.save(profile.id, captured)
        learned = {
            "last_user_id": captured.get("user_id"),
            "display_name": captured.get("user_name"),
            "product": captured.get("product"),
        }
        changed = {
            key: value
            for key, value in learned.items()
            if value and value != getattr(profile, key, None)
        }
        # Handled apart from the loop above: False is a real answer here, and
        # `if value` would throw it away.
        if "institution_selected" in captured:
            flag = bool(captured["institution_selected"])
            if flag != profile.institution_selected:
                changed["institution_selected"] = flag
        if changed:
            self._store.update(profile.id, **changed)

    def cancel(self, profile_id: str) -> bool:
        with self._lock:
            queued = [item for item in self._queue if item[0] == profile_id]
            for item in queued:
                self._queue.remove(item)
        if queued:
            self._finish(profile_id, RunStatus.CANCELLED, "Cancelado antes de iniciar")
            return True

        task = self._tasks.get(profile_id)
        if task and not task.done():
            # Ask the backend first: killing a container is cleaner than
            # unwinding the task that is waiting on it.
            asyncio.create_task(self.backend.cancel(profile_id))
            task.cancel()
            return True
        return False

    def _finish(self, profile_id: str, status: RunStatus, error: str | None) -> None:
        with self._lock:
            record = self._records.setdefault(profile_id, RunRecord(profile_id))
            record.status = status
            record.error = error
            record.finished_at = _now()

    # ------------------------------------------------------------------
    # Log and event ingestion
    # ------------------------------------------------------------------

    def ingest(self, profile_id: str, line: str) -> None:
        """Take one line from a run: either a structured event or a log line."""
        event = events.parse(line)
        if event is not None:
            self._apply_event(profile_id, event)
            return
        with self._lock:
            record = self._records.get(profile_id)
            if record is None:
                return
            record.logs.append(_redact(line))
            record.total_lines += 1

    def ingest_in_process(self, line: str) -> None:
        """Route a root-logger line to the run that owns this process."""
        with self._lock:
            profile_id = self._in_process_profile
        if profile_id:
            self.ingest(profile_id, line)

    def _apply_event(self, profile_id: str, event: dict[str, Any]) -> None:
        if event.get("type") != "path_done":
            return
        with self._lock:
            record = self._records.get(profile_id)
            if record is None:
                return
            if event.get("ok"):
                record.paths_done += 1
            else:
                record.paths_failed += 1
            record.paths_total = event.get("total") or record.paths_total

            # Kept as-is, not coerced: Foundations numbers its units and
            # lessons, Fluency names them. int() on a lesson title would raise
            # inside the lock and stop the whole feed.
            course = str(event.get("course", "?"))
            unit = event.get("unit")
            lesson = event.get("lesson")
            key = f"{course}|{unit}|{lesson}"
            progress = record.lessons.get(key)
            if progress is None:
                if len(record.lessons) >= MAX_LESSONS_TRACKED:
                    return
                progress = LessonProgress(course=course, unit=unit, lesson=lesson)
                record.lessons[key] = progress
            if event.get("ok"):
                progress.ok += 1
            else:
                progress.failed += 1

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def record_for(self, profile_id: str) -> RunRecord:
        with self._lock:
            return self._records.setdefault(profile_id, RunRecord(profile_id))

    def logs_since(self, profile_id: str, since: int) -> tuple[list[str], int]:
        """Return log lines after index *since*, plus the new cursor."""
        with self._lock:
            record = self._records.get(profile_id)
            if record is None:
                return [], 0
            buffered = len(record.logs)
            first_index = record.total_lines - buffered
            start = max(0, since - first_index)
            return list(record.logs)[start:], record.total_lines

    def queue_position(self, profile_id: str) -> int | None:
        with self._lock:
            for position, (queued_id, _, _) in enumerate(self._queue):
                if queued_id == profile_id:
                    return position + 1
        return None

    def progress_for(self, profile: Profile) -> dict[str, Any]:
        """Read the account's persisted progress straight from its state file.

        The two products write different files: Foundations uses
        ``<user_id>.json`` and Fluency ``fluency_<user_id>.json``. Both are
        checked and added, so a profile shows its progress whichever product it
        turned out to have — and keeps showing it if the account has both.
        """
        empty = {"total_done": 0, "done_today": 0, "last_run": None}
        try:
            states = [StateStore(self._state_dir).load(profile.last_user_id, profile.email)]
            fluency = self._fluency_state(profile)
            if fluency is not None:
                states.append(fluency)
        except Exception:  # noqa: BLE001 - a missing state dir is not an error
            return empty

        last_runs = [s.last_run() for s in states if s.last_run()]
        return {
            "total_done": sum(s.total_done() for s in states),
            "done_today": sum(s.count_done_today() for s in states),
            "last_run": max(last_runs) if last_runs else None,
        }

    def _fluency_state(self, profile: Profile):
        """The Fluency state file for this account, if it exists."""
        key = profile.last_user_id or profile.email or "default_account"
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(key))
        path = self._state_dir / f"fluency_{safe}.json"
        if not path.exists():
            return None
        from rosseta_stone_script_a.infrastructure.state.run_progress_state import (
            RunProgressState,
        )

        return RunProgressState(path)


class RunAlreadyActive(RuntimeError):
    """Raised when a profile already has a queued or running job."""

    def __init__(self, profile_id: str) -> None:
        super().__init__(f"Profile {profile_id} already has an active run")
        self.profile_id = profile_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
