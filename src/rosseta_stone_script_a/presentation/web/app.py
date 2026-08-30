"""FastAPI application for the multi-profile web UI.

A sibling of ``presentation/cli.py``: same orchestrators, same
``DependencyFactory``, different way in. Nothing under ``application/`` or
``domain/`` knows this layer exists.

Auth is a single shared token read from ``ROSETTA_WEB_TOKEN``. When it is unset
the API is open, which is fine for ``127.0.0.1`` but *not* for a published
container port — the API can launch runs with stored credentials.
"""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from rosseta_stone_script_a.infrastructure.core import get_base_dir, get_settings

from .models import ProfileIn, ProfileUpdate, RunIn
from .profiles import ProfileStore
from .run_manager import RunAlreadyActive, RunManager

STATIC_DIR = Path(__file__).parent / "static"


def _require_token(request: Request) -> None:
    """Reject the request unless it carries the configured shared token."""
    expected = os.getenv("ROSETTA_WEB_TOKEN", "").strip()
    if not expected:
        return
    supplied = request.headers.get("x-auth-token") or request.query_params.get("token")
    if not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Token invalido o ausente")


def create_app(
    store: ProfileStore | None = None,
    state_dir: Path | None = None,
    backend: Any | None = None,
) -> FastAPI:
    """Build the app. Injectable arguments exist so tests can use temp dirs."""
    profile_store = store or ProfileStore()
    if state_dir is None:
        settings = get_settings().rosseta_settings
        state_dir = get_base_dir() / settings.rosetta_state_dir
    manager = RunManager(profile_store, state_dir, backend=backend)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        manager.start()
        yield
        await manager.shutdown()

    app = FastAPI(title="Rosseta Stone Bot", lifespan=lifespan)
    app.state.store = profile_store
    app.state.manager = manager
    guard = [Depends(_require_token)]

    def _profile_view(profile) -> dict[str, Any]:
        record = manager.record_for(profile.id)
        return {
            **profile.public_dict(),
            "run": record.public_dict(),
            "queue_position": manager.queue_position(profile.id),
            "progress": manager.progress_for(profile),
            # Identifiers in the clear, credentials fingerprinted. The real
            # values stay in state/sessions/<id>.json and never cross HTTP.
            "session": manager.sessions.masked(profile.id),
        }

    def _get_or_404(profile_id: str):
        profile = profile_store.get(profile_id)
        if profile is None:
            raise HTTPException(status_code=404, detail="Perfil no encontrado")
        return profile

    # ------------------------------------------------------------------
    # Profiles
    # ------------------------------------------------------------------

    @app.get("/api/profiles", dependencies=guard)
    def list_profiles() -> dict[str, Any]:
        return {"profiles": [_profile_view(p) for p in profile_store.list()]}

    @app.post("/api/profiles", status_code=201, dependencies=guard)
    def create_profile(payload: ProfileIn) -> dict[str, Any]:
        data = payload.model_dump()
        # The UI only sends email and password. Name it after the mailbox until
        # a run reports the account's real name.
        if not data.get("name"):
            data["name"] = data["email"].split("@")[0]
        profile = profile_store.create(**data)
        return _profile_view(profile)

    @app.patch("/api/profiles/{profile_id}", dependencies=guard)
    def update_profile(profile_id: str, payload: ProfileUpdate) -> dict[str, Any]:
        _get_or_404(profile_id)
        changes = payload.model_dump(exclude_unset=True)
        # An omitted password keeps the stored one; an empty string clears it.
        if "password" in changes and changes["password"] == "":
            changes["password"] = None
        profile = profile_store.update(profile_id, **changes)
        return _profile_view(profile)

    @app.delete("/api/profiles/{profile_id}", dependencies=guard)
    def delete_profile(profile_id: str) -> dict[str, bool]:
        _get_or_404(profile_id)
        record = manager.record_for(profile_id)
        if record.status.value in ("running", "queued"):
            raise HTTPException(
                status_code=409, detail="No se puede borrar un perfil en ejecucion"
            )
        # Deleting the account must take its credentials with it.
        manager.sessions.delete(profile_id)
        return {"deleted": profile_store.delete(profile_id)}

    # ------------------------------------------------------------------
    # Runs
    # ------------------------------------------------------------------

    @app.post("/api/profiles/{profile_id}/run", dependencies=guard)
    async def start_run(
        profile_id: str, payload: RunIn | None = None
    ) -> dict[str, Any]:
        profile = _get_or_404(profile_id)
        password = (payload.password if payload else None) or profile.password
        if not password:
            raise HTTPException(
                status_code=400,
                detail="Este perfil no guarda contrasena: enviala con la peticion",
            )
        try:
            manager.enqueue(profile_id, password)
        except RunAlreadyActive:
            raise HTTPException(
                status_code=409, detail="Este perfil ya tiene una corrida activa"
            )
        return _profile_view(profile)

    @app.post("/api/profiles/{profile_id}/verify", dependencies=guard)
    async def verify_profile(
        profile_id: str, payload: RunIn | None = None
    ) -> dict[str, Any]:
        """Log in and report what the account is, without sending anything."""
        profile = _get_or_404(profile_id)
        password = (payload.password if payload else None) or profile.password
        if not password:
            raise HTTPException(
                status_code=400,
                detail="Este perfil no guarda contrasena: enviala con la peticion",
            )
        try:
            manager.enqueue(profile_id, password, mode="verify")
        except RunAlreadyActive:
            raise HTTPException(
                status_code=409, detail="Este perfil ya tiene una corrida activa"
            )
        return _profile_view(profile)

    @app.post("/api/profiles/{profile_id}/pending", dependencies=guard)
    async def inspect_pending(
        profile_id: str, payload: RunIn | None = None
    ) -> dict[str, Any]:
        """Read Fluency's real progress and reconcile the local cache."""
        profile = _get_or_404(profile_id)
        password = (payload.password if payload else None) or profile.password
        if not password:
            raise HTTPException(status_code=400, detail="Este perfil no guarda contrasena: enviala con la peticion")
        try:
            manager.enqueue(profile_id, password, mode="pending")
        except RunAlreadyActive:
            raise HTTPException(status_code=409, detail="Este perfil ya tiene una corrida activa")
        return _profile_view(profile)

    @app.post("/api/profiles/{profile_id}/stop", dependencies=guard)
    async def stop_run(profile_id: str) -> dict[str, Any]:
        _get_or_404(profile_id)
        stopped = manager.cancel(profile_id)
        if not stopped:
            raise HTTPException(status_code=409, detail="No hay corrida que detener")
        return _profile_view(_get_or_404(profile_id))

    @app.get("/api/profiles/{profile_id}/logs", dependencies=guard)
    def read_logs(profile_id: str, since: int = 0) -> dict[str, Any]:
        _get_or_404(profile_id)
        lines, cursor = manager.logs_since(profile_id, since)
        record = manager.record_for(profile_id)
        return {
            "lines": lines,
            "cursor": cursor,
            "status": record.status.value,
            "error": record.error,
        }

    # ------------------------------------------------------------------
    # Meta
    # ------------------------------------------------------------------

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "profiles": len(profile_store.list()),
            "auth_required": bool(os.getenv("ROSETTA_WEB_TOKEN", "").strip()),
            "backend": manager.backend_name,
            "parallel": getattr(manager.backend, "supports_parallel", False),
        }

    @app.get("/")
    def index():
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            return JSONResponse(
                {"error": "UI no encontrada", "path": str(index_file)}, status_code=500
            )
        return FileResponse(index_file)

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app
