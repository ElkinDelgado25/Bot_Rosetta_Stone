"""Serialised, per-profile run execution for the web UI.

Only one run executes at a time: it drives a real browser and writes the
per-account state file, and two concurrent runs would fight over both. Requests
for a busy manager are queued FIFO and reported as ``queued`` until their turn.

Live progress is *not* tracked in memory. ``complete_foundations`` persists the
state file after every accepted POST, so re-reading ``RunProgressState`` gives
the true count mid-run and survives a restart. See ``progress_for``.
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

from rosseta_stone_script_a.domain.entities.credentials import Credentials
from rosseta_stone_script_a.infrastructure.core import get_settings
from rosseta_stone_script_a.infrastructure.state.state_store import StateStore
from rosseta_stone_script_a.presentation.cli import RosettaCLI

from .profiles import Profile, ProfileStore

MAX_LOG_LINES = 2000

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
class RunRecord:
    """The latest (or in-flight) run for one profile."""

    profile_id: str
    status: RunStatus = RunStatus.IDLE
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=MAX_LOG_LINES))
    # Total lines ever appended, so a client that reconnects knows how many it
    # missed even after the deque has dropped the oldest ones.
    total_lines: int = 0

    def public_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
            "total_lines": self.total_lines,
        }


class _RunLogHandler(logging.Handler):
    """Feeds root-logger records into the active run's buffer."""

    def __init__(self, manager: "RunManager") -> None:
        super().__init__(level=logging.INFO)
        self._manager = manager

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = _redact(record.getMessage())
        except Exception:  # noqa: BLE001 - a broken log must not kill a run
            return
        stamp = datetime.now().strftime("%H:%M:%S")
        self._manager._append_log(f"{stamp} {record.levelname:<7} {message}")


class RunManager:
    """Owns the run queue, the active task, and each profile's last result."""

    def __init__(self, store: ProfileStore, state_dir: Path) -> None:
        self._store = store
        self._state_dir = state_dir
        self._records: dict[str, RunRecord] = {}
        self._queue: deque[tuple[str, str | None]] = deque()
        self._active_profile_id: str | None = None
        self._active_task: asyncio.Task | None = None
        self._lock = Lock()
        self._handler = _RunLogHandler(self)
        self._worker: asyncio.Task | None = None
        # Guarded by _lock, and flipped in the same critical section that
        # checks the queue: a Task's own `done()` lags the loop by a tick, so
        # relying on it lets an enqueue land in a queue nobody will drain.
        self._worker_running = False
        self._handler_attached = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Attach the log handler so runs stream into their record."""
        if not self._handler_attached:
            logging.getLogger().addHandler(self._handler)
            self._handler_attached = True

    async def shutdown(self) -> None:
        logging.getLogger().removeHandler(self._handler)
        self._handler_attached = False
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        if self._worker and not self._worker.done():
            self._worker.cancel()

    # ------------------------------------------------------------------
    # Queueing
    # ------------------------------------------------------------------

    def enqueue(self, profile_id: str, password_override: str | None = None) -> RunRecord:
        """Queue a run for *profile_id*, or raise if one is already pending."""
        with self._lock:
            record = self._records.get(profile_id)
            if record and record.status in (RunStatus.RUNNING, RunStatus.QUEUED):
                raise RunAlreadyActive(profile_id)

            record = RunRecord(profile_id=profile_id, status=RunStatus.QUEUED)
            self._records[profile_id] = record
            self._queue.append((profile_id, password_override))
            needs_worker = not self._worker_running
            if needs_worker:
                self._worker_running = True

        self.start()
        if needs_worker:
            self._worker = asyncio.create_task(self._drain_queue())
        return record

    def cancel(self, profile_id: str) -> bool:
        """Cancel a queued run, or stop the active one."""
        with self._lock:
            queued = [item for item in self._queue if item[0] == profile_id]
            for item in queued:
                self._queue.remove(item)
            if queued:
                self._finish(profile_id, RunStatus.CANCELLED, "Cancelado antes de iniciar")
                return True
            is_active = self._active_profile_id == profile_id

        if is_active and self._active_task and not self._active_task.done():
            self._active_task.cancel()
            return True
        return False

    async def _drain_queue(self) -> None:
        # The finally clears the flag on every exit path — clean drain, crash,
        # or shutdown cancellation. Leaving it set would wedge the queue: no
        # later enqueue would ever start a replacement worker.
        try:
            while True:
                with self._lock:
                    if not self._queue:
                        break
                    profile_id, password_override = self._queue.popleft()
                    self._active_profile_id = profile_id

                profile = self._store.get(profile_id)
                if profile is None:
                    self._finish(profile_id, RunStatus.ERROR, "El perfil ya no existe")
                    continue

                self._active_task = asyncio.create_task(
                    self._execute(profile, password_override)
                )
                try:
                    await self._active_task
                except asyncio.CancelledError:
                    self._finish(
                        profile_id, RunStatus.CANCELLED, "Detenido por el usuario"
                    )
                finally:
                    self._active_task = None
        finally:
            with self._lock:
                self._active_profile_id = None
                self._worker_running = False

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def _execute(self, profile: Profile, password_override: str | None) -> None:
        password = password_override or profile.password
        if not password:
            self._finish(
                profile.id, RunStatus.ERROR, "El perfil no tiene contraseña guardada"
            )
            return

        with self._lock:
            record = self._records[profile.id]
            record.status = RunStatus.RUNNING
            record.started_at = _now()
            record.logs.clear()
            record.total_lines = 0

        settings = get_settings().rosseta_settings
        try:
            captured = await RosettaCLI().enter_rosetta(
                rosseta_login_url=settings.rosetta_login_url,
                user_credentials=Credentials(email=profile.email, password=password),
                units_to_complete=profile.units_to_complete,
                lessons_to_complete=profile.lessons_to_complete,
                path_types_to_complete=profile.path_types_to_complete,
                target_score_percent=profile.target_score_percent,
                force_recomplete=profile.force_recomplete,
                human_mode=profile.human_mode,
                max_paths_per_day=profile.max_paths_per_day,
                state_dir=self._state_dir,
                headless=True,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI, not swallowed
            logging.getLogger("app").exception("La corrida falló")
            self._finish(profile.id, RunStatus.ERROR, str(exc) or exc.__class__.__name__)
            return

        # Remember the tracking user_id so progress can find the state file
        # before the next run starts.
        user_id = (captured or {}).get("user_id")
        if user_id and user_id != profile.last_user_id:
            self._store.update(profile.id, last_user_id=user_id)

        self._finish(profile.id, RunStatus.SUCCESS, None)

    def _finish(self, profile_id: str, status: RunStatus, error: str | None) -> None:
        with self._lock:
            record = self._records.setdefault(profile_id, RunRecord(profile_id=profile_id))
            record.status = status
            record.error = error
            record.finished_at = _now()

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def _append_log(self, line: str) -> None:
        with self._lock:
            profile_id = self._active_profile_id
            if profile_id is None:
                return
            record = self._records.get(profile_id)
            if record is None:
                return
            record.logs.append(line)
            record.total_lines += 1

    def record_for(self, profile_id: str) -> RunRecord:
        with self._lock:
            return self._records.setdefault(
                profile_id, RunRecord(profile_id=profile_id)
            )

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
            for position, (queued_id, _) in enumerate(self._queue):
                if queued_id == profile_id:
                    return position + 1
        return None

    def progress_for(self, profile: Profile) -> dict[str, Any]:
        """Read the account's persisted progress straight from its state file."""
        try:
            state = StateStore(self._state_dir).load(
                profile.last_user_id, profile.email
            )
        except Exception:  # noqa: BLE001 - a missing state dir is not an error
            return {"total_done": 0, "done_today": 0, "last_run": None}
        return {
            "total_done": state.total_done(),
            "done_today": state.count_done_today(),
            "last_run": state.last_run(),
        }


class RunAlreadyActive(RuntimeError):
    """Raised when a profile already has a queued or running job."""

    def __init__(self, profile_id: str) -> None:
        super().__init__(f"Profile {profile_id} already has an active run")
        self.profile_id = profile_id


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
