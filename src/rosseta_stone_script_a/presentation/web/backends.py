"""How a run actually executes: in this process, or in its own container.

``DockerBackend`` is what the deployed stack uses — one ephemeral container per
user, all of them in parallel, Playwright and Chromium confined inside. If a
browser wedges, its container dies alone.

``InProcessBackend`` is the fallback for ``uv run rosseta-web`` on a laptop,
where there is no Docker socket. Same behaviour, no isolation, and runs are
serialised by the caller because they share one browser and one state file.

The backend is chosen at startup by ``select_backend``.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from rosseta_stone_script_a.domain.entities.credentials import Credentials
from rosseta_stone_script_a.shared.mixins import LoggingMixin

from .profiles import Profile

LogSink = Callable[[str], None]

WORKER_COMMAND = ["python", "-m", "rosseta_stone_script_a.presentation.worker"]
DEFAULT_IMAGE = "rosseta-script-a:latest"
CONTAINER_DATA_DIR = "/data"


@dataclass
class RunOutcome:
    ok: bool
    error: str | None = None
    captured: dict[str, Any] = field(default_factory=dict)


def _run_config(
    profile: Profile, password: str, state_dir: str, login_url: str, mode: str
) -> dict:
    return {
        "profile_id": profile.id,
        "mode": mode,
        "email": profile.email,
        "password": password,
        "units_to_complete": profile.units_to_complete,
        "lessons_to_complete": profile.lessons_to_complete,
        "path_types_to_complete": profile.path_types_to_complete,
        "target_score_percent": profile.target_score_percent,
        "force_recomplete": profile.force_recomplete,
        "human_mode": profile.human_mode,
        "max_paths_per_day": profile.max_paths_per_day,
        "state_dir": state_dir,
        "login_url": login_url,
    }


class InProcessBackend(LoggingMixin):
    """Runs inside the web process. No isolation; used when Docker is absent."""

    name = "in-process"
    supports_parallel = False

    def __init__(self, state_dir: Path, login_url: str) -> None:
        self._state_dir = state_dir
        self._login_url = login_url
        self._tasks: dict[str, asyncio.Task] = {}

    async def run(
        self, profile: Profile, password: str, sink: LogSink, mode: str = "run"
    ) -> RunOutcome:
        # Log lines reach the UI through the root-logger handler the RunManager
        # installs, so nothing is pushed into `sink` here.
        from rosseta_stone_script_a.presentation.cli import RosettaCLI

        task = asyncio.create_task(
            RosettaCLI().enter_rosetta(
                rosseta_login_url=self._login_url,
                user_credentials=Credentials(
                    email=profile.email, password=password
                ),
                units_to_complete=profile.units_to_complete,
                lessons_to_complete=profile.lessons_to_complete,
                path_types_to_complete=profile.path_types_to_complete,
                target_score_percent=profile.target_score_percent,
                force_recomplete=profile.force_recomplete,
                human_mode=profile.human_mode,
                max_paths_per_day=profile.max_paths_per_day,
                state_dir=self._state_dir,
                headless=True,
                verify_only=mode == "verify",
            )
        )
        self._tasks[profile.id] = task
        try:
            captured = await task
            return RunOutcome(ok=True, captured=captured or {})
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            return RunOutcome(ok=False, error=str(exc) or exc.__class__.__name__)
        finally:
            self._tasks.pop(profile.id, None)

    async def cancel(self, profile_id: str) -> bool:
        task = self._tasks.get(profile_id)
        if task and not task.done():
            task.cancel()
            return True
        return False


class DockerBackend(LoggingMixin):
    """Runs each user in its own throwaway container."""

    name = "docker"
    supports_parallel = True

    def __init__(self, state_dir: Path, login_url: str, client: Any) -> None:
        self._state_dir = state_dir
        self._login_url = login_url
        self._client = client
        self._containers: dict[str, Any] = {}
        self._image = os.getenv("ROSETTA_WORKER_IMAGE", DEFAULT_IMAGE)

    # ------------------------------------------------------------------
    # Volume plumbing
    # ------------------------------------------------------------------

    def _host_data_path(self) -> str | None:
        """Find the host path behind /data, so the worker can mount the same one.

        A bind mount inside this container points at a host directory the worker
        must also see; but from in here we only know the container-side path.
        Ask Docker what our own /data is bound to.
        """
        override = os.getenv("ROSETTA_DATA_HOST_PATH", "").strip()
        if override:
            return override
        try:
            me = self._client.containers.get(socket.gethostname())
            for mount in me.attrs.get("Mounts", []):
                if mount.get("Destination") == CONTAINER_DATA_DIR:
                    return mount.get("Source")
        except Exception:  # noqa: BLE001 - not fatal, reported by the caller
            self.logger.debug("No se pudo determinar el bind de /data", exc_info=True)
        return None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def run(
        self, profile: Profile, password: str, sink: LogSink, mode: str = "run"
    ) -> RunOutcome:
        host_data = self._host_data_path()
        if not host_data:
            return RunOutcome(
                ok=False,
                error=(
                    "No se pudo resolver la ruta de /data en el host. "
                    "Define ROSETTA_DATA_HOST_PATH."
                ),
            )

        run_id = uuid.uuid4().hex[:10]
        runs_dir = self._state_dir.parent / "runs"
        runs_dir.mkdir(parents=True, exist_ok=True)
        config_path = runs_dir / f"{run_id}.json"

        # The worker reads its config from the shared volume, not from the
        # environment: `docker inspect` shows env vars, and this holds a
        # password.
        config = _run_config(
            profile,
            password,
            state_dir=str(self._container_path(self._state_dir)),
            login_url=self._login_url,
            mode=mode,
        )
        fd = os.open(str(config_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False)

        container = None
        try:
            container = await asyncio.to_thread(
                self._client.containers.run,
                self._image,
                command=WORKER_COMMAND,
                detach=True,
                name=f"rosetta-{mode}-{profile.id}-{run_id}",
                environment={
                    "ROSETTA_RUN_CONFIG": str(
                        self._container_path(config_path)
                    ),
                    "ROSETTA_HOME": CONTAINER_DATA_DIR,
                    "ROSETTA_EVENTS": "1",
                    "BROWSER_HEADLESS": "true",
                    "BROWSER_CHANNEL": "",
                    "PYTHONUNBUFFERED": "1",
                },
                volumes={host_data: {"bind": CONTAINER_DATA_DIR, "mode": "rw"}},
                shm_size="512m",
                # No docker socket here: a worker must not be able to spawn
                # containers of its own.
                labels={"rosetta.profile": profile.id, "rosetta.run": run_id},
            )
            self._containers[profile.id] = container
            sink(f"Contenedor {container.short_id} iniciado para {profile.email}")

            await self._stream_logs(container, sink)
            result = await asyncio.to_thread(container.wait)
            exit_code = result.get("StatusCode", 1)

            outcome = self._read_result(config_path, exit_code)
            sink(f"Contenedor terminado con código {exit_code}")
            return outcome
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - reported to the UI
            return RunOutcome(ok=False, error=str(exc) or exc.__class__.__name__)
        finally:
            self._containers.pop(profile.id, None)
            await self._cleanup(container, config_path)

    def _container_path(self, host_side: Path) -> Path:
        """Translate a path in this container to the same path in the worker.

        Both mount the same volume at the same place, so the only difference is
        when the orchestrator runs outside a container.
        """
        try:
            relative = Path(host_side).relative_to(self._state_dir.parent)
        except ValueError:
            return Path(host_side)
        return Path(CONTAINER_DATA_DIR) / relative

    async def _stream_logs(self, container: Any, sink: LogSink) -> None:
        """Pump the container's stdout into the UI as it happens."""

        def pump() -> None:
            for chunk in container.logs(stream=True, follow=True):
                for line in chunk.decode("utf-8", "replace").splitlines():
                    if line.strip():
                        sink(line)

        await asyncio.to_thread(pump)

    def _read_result(self, config_path: Path, exit_code: int) -> RunOutcome:
        result_path = config_path.with_suffix(".result.json")
        payload: dict[str, Any] = {}
        if result_path.exists():
            try:
                with open(result_path, encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError):
                payload = {}

        if exit_code == 0 and payload.get("ok"):
            return RunOutcome(ok=True, captured=payload.get("captured") or {})
        error = payload.get("error") or f"El worker terminó con código {exit_code}"
        return RunOutcome(ok=False, error=error, captured=payload.get("captured") or {})

    async def _cleanup(self, container: Any, config_path: Path) -> None:
        # The config holds a password and the result holds session tokens:
        # neither outlives the run.
        for path in (config_path, config_path.with_suffix(".result.json")):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                self.logger.warning("No se pudo borrar %s", path)
        if container is not None:
            try:
                await asyncio.to_thread(container.remove, force=True)
            except Exception:  # noqa: BLE001 - already gone is fine
                self.logger.debug("El contenedor ya no existía", exc_info=True)

    async def cancel(self, profile_id: str) -> bool:
        container = self._containers.get(profile_id)
        if container is None:
            return False
        try:
            await asyncio.to_thread(container.kill)
            return True
        except Exception:  # noqa: BLE001 - it may have just finished
            return False


def _running_in_container() -> bool:
    """Whether this process is itself inside a container.

    It matters because a worker has to mount the *host* path behind /data, and
    that is only knowable from inside — a developer running the server straight
    on their laptop has a Docker daemon but no volume to hand down.
    """
    return Path("/.dockerenv").exists() or bool(
        os.getenv("ROSETTA_DATA_HOST_PATH", "").strip()
    )


def select_backend(state_dir: Path, login_url: str) -> InProcessBackend | DockerBackend:
    """Pick the container backend when it can actually work; else in-process."""
    forced = os.getenv("ROSETTA_RUN_BACKEND", "").strip().lower()
    if forced == "in-process":
        return InProcessBackend(state_dir, login_url)

    if forced != "docker" and not _running_in_container():
        # Docker Desktop on a laptop answers the socket happily, but a run
        # launched from there could not share this process's data directory.
        return InProcessBackend(state_dir, login_url)

    try:
        import docker  # noqa: PLC0415 - optional dependency

        client = docker.from_env()
        client.ping()
        return DockerBackend(state_dir, login_url, client)
    except Exception:  # noqa: BLE001 - no socket, no SDK, no daemon
        return InProcessBackend(state_dir, login_url)
