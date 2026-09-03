"""Read-only reconciliation of Fluency Builder activity progress."""

from __future__ import annotations

from typing import Any

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    fluency_activity_key,
)
from Resolucion_script_rosseta.aplicacion.ports.fluency_api import FluencyApiPort
from Resolucion_script_rosseta.dominio.errors import SessionCaptureIncomplete
from Resolucion_script_rosseta.infraestructura.state import RunProgressState
from Resolucion_script_rosseta.compartido.mixins import LoggingMixin


class FluencyPendingOrchestrator(LoggingMixin):
    """Compare the authoritative platform state with the local resume cache."""

    def __init__(self, api_port: FluencyApiPort, state_dir) -> None:
        self.api_port = api_port
        self.state_dir = state_dir

    async def execute(self, captured_data: dict[str, Any]) -> dict[str, Any]:
        authorization = captured_data.get("authorization") or ""
        user_id = captured_data.get("user_id")
        if not authorization:
            raise SessionCaptureIncomplete(["authorization"], product="Fluency Builder")

        state = self._state_for(user_id, captured_data)
        locale = captured_data.get("lang_code")
        catalog = await self.api_port.get_catalog(authorization, locale=locale)

        completed: list[dict[str, str]] = []
        pending: list[dict[str, str]] = []
        recovered = 0
        for course in catalog.courses:
            titles = {sequence.sequence_id: sequence.title or "Lección sin título"
                      for sequence in course.sequences}
            progress = await self.api_port.get_progress(authorization, course.course_id)
            for progress_course in progress or []:
                for sequence in progress_course.get("sequences") or []:
                    sequence_id = sequence.get("sequenceId")
                    lesson = titles.get(sequence_id, "Lección sin título")
                    for activity in sequence.get("activities") or []:
                        activity_id = activity.get("activityId")
                        if not activity_id or not sequence_id:
                            continue
                        item = {
                            "course": course.title or "Curso sin título",
                            "lesson": lesson,
                            "activity_id": activity_id,
                        }
                        if (activity.get("percentComplete") or 0) >= 1:
                            completed.append(item)
                            if state.remember_done(
                                fluency_activity_key(course.course_id, sequence_id, activity_id)
                            ):
                                recovered += 1
                        else:
                            pending.append(item)

        state.save()
        self.logger.info(
            "Consulta de pendientes terminada: %s completas, %s pendientes, %s recuperadas en memoria",
            len(completed), len(pending), recovered,
        )
        return {"completed": completed, "pending": pending, "recovered": recovered}

    def _state_for(self, user_id: str | None, captured: dict[str, Any]) -> RunProgressState:
        email = (captured.get("credentials") or {}).get("email")
        key = user_id or email or "default_account"
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(key))
        return RunProgressState(self.state_dir / f"fluency_{safe}.json")

