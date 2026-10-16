"""Read-only reconciliation of Fluency Builder activity progress."""

from __future__ import annotations

from typing import Any

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    BROWSER_COMPLETED_TYPES,
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
        seen_pending: set[tuple[str, str, str]] = set()
        for course in catalog.courses:
            titles = {sequence.sequence_id: sequence.title or "Lección sin título"
                      for sequence in course.sequences}
            progress = await self.api_port.get_progress(authorization, course.course_id)
            for progress_course in progress or []:
                for sequence in progress_course.get("sequences") or []:
                    sequence_id = sequence.get("sequenceId")
                    lesson = titles.get(sequence_id, "Lección sin título")
                    listed = sequence.get("activities") or []
                    listed_complete = {
                        activity.get("activityId")
                        for activity in listed
                        if activity.get("activityId")
                        and (activity.get("percentComplete") or 0) >= 1
                    }
                    for activity in listed:
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
                            seen_pending.add((course.course_id, sequence_id, activity_id))

                    count = sequence.get("countOfActivities") or 0
                    if sequence_id and (
                        count > len(listed) or count > len(listed_complete)
                    ):
                        await self._append_omitted_tree(
                            authorization,
                            locale,
                            course,
                            sequence_id,
                            lesson,
                            listed_complete,
                            pending,
                            seen_pending,
                        )

        state.save()
        self.logger.info(
            "Consulta de pendientes terminada: %s completas, %s pendientes, %s recuperadas en memoria",
            len(completed), len(pending), recovered,
        )
        return {"completed": completed, "pending": pending, "recovered": recovered}

    async def _append_omitted_tree(
        self,
        authorization,
        locale,
        course,
        sequence_id,
        lesson,
        listed_complete,
        pending,
        seen_pending,
    ) -> None:
        """getProgress sometimes drops tree conversations; getSequence still has them."""
        try:
            sequence = await self.api_port.get_sequence(
                authorization,
                course_id=course.course_id,
                sequence_id=sequence_id,
                locale=locale,
            )
        except Exception as error:  # noqa: BLE001 - la consulta no puede hundirse
            self.logger.info(
                "  No se pudo leer getSequence de %s / %s: %s",
                course.title, lesson, error,
            )
            return
        for activity in sequence.activities:
            if activity.activity_type not in BROWSER_COMPLETED_TYPES:
                continue
            if activity.activity_id in listed_complete:
                continue
            key = (course.course_id, sequence_id, activity.activity_id)
            if key in seen_pending:
                continue
            seen_pending.add(key)
            pending.append({
                "course": course.title or "Curso sin título",
                "lesson": lesson,
                "activity_id": activity.activity_id,
            })

    def _state_for(self, user_id: str | None, captured: dict[str, Any]) -> RunProgressState:
        email = (captured.get("credentials") or {}).get("email")
        key = user_id or email or "default_account"
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(key))
        return RunProgressState(self.state_dir / f"fluency_{safe}.json")
