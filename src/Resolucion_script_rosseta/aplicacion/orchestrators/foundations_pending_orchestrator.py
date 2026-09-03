"""Read-only reconciliation of Foundations progress with its local cache."""

from __future__ import annotations

from typing import Any

from Resolucion_script_rosseta.aplicacion.ports.foundations_api import FoundationsApiPort
from Resolucion_script_rosseta.dominio.errors import SessionCaptureIncomplete
from Resolucion_script_rosseta.infraestructura.state import StateStore, make_path_key
from Resolucion_script_rosseta.compartido.mixins import LoggingMixin


class FoundationsPendingOrchestrator(LoggingMixin):
    """Read Rosetta's current menu and remember externally completed paths."""

    def __init__(self, api_port: FoundationsApiPort, state_dir) -> None:
        self.api_port = api_port
        self.state_dir = state_dir

    async def execute(self, captured_data: dict[str, Any]) -> dict[str, Any]:
        authorization = captured_data.get("authorization") or ""
        language_code = captured_data.get("lang_code") or ""
        missing = [
            name for name, value in (("authorization", authorization), ("lang_code", language_code))
            if not value
        ]
        if missing:
            raise SessionCaptureIncomplete(missing, product="Foundations")

        menu = await self.api_port.get_course_menu(authorization, language_code)
        credentials = captured_data.get("credentials") or {}
        state = StateStore(self.state_dir).load(
            captured_data.get("user_id"), credentials.get("email")
        )
        completed: list[dict[str, str]] = []
        pending: list[dict[str, str]] = []
        recovered = 0
        for unit in menu.units:
            for lesson in unit.lessons:
                for path in lesson.paths:
                    item = {
                        "course": path.course or menu.current_course_id,
                        "lesson": f"Unidad {unit.unit_number} · Lección {lesson.lesson_number}",
                        "activity_id": path.type,
                    }
                    if path.complete or path.percent_complete >= 100:
                        completed.append(item)
                        if state.remember_done(make_path_key(path)):
                            recovered += 1
                    else:
                        pending.append(item)

        state.save()
        self.logger.info(
            "Consulta de pendientes Foundations terminada: %s completas, %s pendientes, %s recuperadas en memoria",
            len(completed), len(pending), recovered,
        )
        return {"completed": completed, "pending": pending, "recovered": recovered}

