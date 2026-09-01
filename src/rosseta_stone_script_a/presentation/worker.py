"""One run, one process — the command an ephemeral worker container executes.

The orchestrator writes a JSON config, starts a container with
``ROSETTA_RUN_CONFIG`` pointing at it, and reads this process's stdout. Progress
travels as structured events (see ``shared.events``) interleaved with the normal
log; the captured session is handed back through a result file, because stdout
is public to anyone reading container logs and the tokens are credentials.

Exit codes: 0 success, 1 run failed, 2 bad configuration.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

CONFIG_ENV = "ROSETTA_RUN_CONFIG"


def _load_config() -> dict[str, Any]:
    raw_path = os.getenv(CONFIG_ENV, "").strip()
    if not raw_path:
        raise SystemExit(f"Falta {CONFIG_ENV}: el worker no sabe qué ejecutar")
    path = Path(raw_path)
    if not path.exists():
        raise SystemExit(f"No existe el archivo de configuración: {path}")
    try:
        # utf-8-sig: a config edited by hand on Windows can carry a BOM, and
        # json.load chokes on it with a traceback that says nothing useful.
        with open(path, encoding="utf-8-sig") as handle:
            config = json.load(handle)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Configuración ilegible ({path}): {exc}") from exc
    except OSError as exc:
        raise SystemExit(f"No se pudo leer {path}: {exc}") from exc

    if not isinstance(config, dict):
        raise SystemExit(f"La configuración de {path} no es un objeto JSON")
    missing = [key for key in ("email", "password", "login_url", "state_dir")
               if not config.get(key)]
    if missing:
        raise SystemExit(f"Faltan campos en la configuración: {missing}")
    return config


def _write_result(config_path: Path, payload: dict[str, Any]) -> None:
    """Hand the captured session back to the orchestrator, out of band."""
    result_path = config_path.with_suffix(".result.json")
    fd = os.open(str(result_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


async def _run(config: dict[str, Any]) -> dict[str, Any]:
    from rosseta_stone_script_a.domain.entities.credentials import Credentials
    from rosseta_stone_script_a.presentation.cli import RosettaCLI

    return await RosettaCLI().enter_rosetta(
        rosseta_login_url=config["login_url"],
        user_credentials=Credentials(
            email=config["email"], password=config["password"]
        ),
        units_to_complete=config.get("units_to_complete") or [],
        lessons_to_complete=config.get("lessons_to_complete") or [],
        path_types_to_complete=config.get("path_types_to_complete") or [],
        target_score_percent=config.get("target_score_percent", 100),
        force_recomplete=config.get("force_recomplete", False),
        human_mode=config.get("human_mode", False),
        max_paths_per_day=config.get("max_paths_per_day", 18),
        state_dir=Path(config["state_dir"]),
        headless=True,
        verify_only=config.get("mode") == "verify",
        pending_only=config.get("mode") == "pending",
        stories_only=config.get("mode") == "stories",
    )


def main() -> int:
    # Events are the whole point of this entry point; turn them on before
    # anything imports the use case.
    os.environ.setdefault("ROSETTA_EVENTS", "1")
    from rosseta_stone_script_a.shared import events

    try:
        config = _load_config()
    except SystemExit as exc:
        print(f"Error de configuración: {exc}", file=sys.stderr, flush=True)
        return 2

    config_path = Path(os.environ[CONFIG_ENV])
    profile_id = config.get("profile_id", "?")

    # El tope de lecciones de Fluency se lee del entorno. El orquestador ya lo
    # pasa así, pero un worker lanzado a mano solo trae el JSON: sin esto
    # heredaría el default del motor (1 lección) y pararía tras la primera.
    if "fluency_max_lessons" in config and not os.getenv("FLUENCY_MAX_LESSONS"):
        limite = config["fluency_max_lessons"]
        os.environ["FLUENCY_MAX_LESSONS"] = "all" if not limite else str(limite)
    events.emit("run_started", profile_id=profile_id, email=config.get("email"))

    try:
        captured = asyncio.run(_run(config)) or {}
    except KeyboardInterrupt:
        events.emit("run_finished", profile_id=profile_id, ok=False, error="cancelado")
        return 130
    except Exception as exc:  # noqa: BLE001 - reported, then surfaced as a code
        from rosseta_stone_script_a.domain.errors import SessionCaptureIncomplete

        message = str(exc) or exc.__class__.__name__
        events.emit("run_finished", profile_id=profile_id, ok=False, error=message)
        print(f"La corrida falló: {message}", file=sys.stderr, flush=True)
        _write_result(config_path, {"ok": False, "error": message, "captured": {}})
        return 3 if isinstance(exc, SessionCaptureIncomplete) else 1

    _write_result(config_path, {"ok": True, "error": None, "captured": captured})
    events.emit(
        "run_finished",
        profile_id=profile_id,
        ok=True,
        user_id=captured.get("user_id"),
        product=captured.get("product"),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
