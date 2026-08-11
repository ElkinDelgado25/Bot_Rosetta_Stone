from typing import Any, Dict, Optional

from rosseta_stone_script_a.application.ports.fluency_api import FluencyApiPort
from rosseta_stone_script_a.application.ports.orchestrator import OrchestratorPort
from rosseta_stone_script_a.domain.entities.fluency_catalog import FluencyCatalog
from rosseta_stone_script_a.domain.entities.fluency_course import FluencyCourse
from rosseta_stone_script_a.domain.entities.fluency_sequence import FluencySequence


class FluencyOrchestrator(OrchestratorPort):
    """Read-only Fluency Builder flow.

    Reads the catalog and one lesson's detail live from gaia-server, logging a
    summary and dumping raw responses to diagnostics. This exercises the reading
    layer end to end and confirms the gaia auth scheme. The write phase
    (fabricating ``AddProgress``) is not implemented yet — see docs/FLUENCY_BUILDER.md.
    """

    def __init__(self, api_port: FluencyApiPort):
        super().__init__()
        self.api_port = api_port

    async def execute(self, captured_data: Dict[str, Any]) -> Optional[FluencyCatalog]:
        authorization = captured_data.get("authorization") or ""
        locale = captured_data.get("lang_code")

        if not authorization:
            self.logger.warning(
                "No gaia authorization captured; relying on request-context "
                "cookies. If reads fail, gaia likely needs a Bearer token."
            )

        self.logger.info("Reading Fluency Builder catalog")
        catalog = await self.api_port.get_catalog(authorization, locale=locale)
        self._log_catalog(catalog)

        target = self._first_pending(catalog)
        if not target:
            self.logger.info("No pending lessons found; nothing to inspect further")
            return catalog

        course, sequence_ref = target
        self.logger.info(
            f"Reading first pending lesson: {course.title!r} / "
            f"{sequence_ref.title!r} ({sequence_ref.percent_complete:.0%})"
        )
        detail = await self.api_port.get_sequence(
            authorization,
            course_id=course.course_id,
            sequence_id=sequence_ref.sequence_id,
            locale=locale,
        )
        self._log_sequence(detail)

        self.logger.info(
            "Fluency read-only pass complete. Write phase (AddProgress) not yet "
            "implemented."
        )
        return catalog

    def _first_pending(self, catalog: FluencyCatalog):
        """Return (course, sequence_ref) for the first lesson below 100%."""
        for course in catalog.courses:
            for seq in course.sequences:
                if seq.percent_complete < 1.0:
                    return course, seq
        return None

    def _log_catalog(self, catalog: FluencyCatalog) -> None:
        total_lessons = sum(len(c.sequences) for c in catalog.courses)
        self.logger.info(
            f"Catalog: {len(catalog.courses)} courses, {total_lessons} lessons"
        )
        for course in catalog.courses:
            done = sum(1 for s in course.sequences if s.percent_complete >= 1.0)
            self.logger.info(
                f"  [{course.cefr}] {course.title} "
                f"({done}/{len(course.sequences)} complete)"
            )

    def _log_sequence(self, sequence: FluencySequence) -> None:
        total_steps = sum(len(a.steps) for a in sequence.activities)
        known = sum(
            1 for a in sequence.activities for s in a.steps if s.correct_answer_ids
        )
        self.logger.info(
            f"Lesson {sequence.title!r}: {len(sequence.activities)} activities, "
            f"{total_steps} steps ({known} with known correct answers)"
        )
