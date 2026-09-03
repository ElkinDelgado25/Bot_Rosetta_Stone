from typing import Any, Dict, Optional

from Resolucion_script_rosseta.aplicacion.ports.orchestrator import OrchestratorPort
from Resolucion_script_rosseta.aplicacion.use_cases.complete_exam import CompleteExamUseCase
from Resolucion_script_rosseta.dominio.entities.exam import ExamStepResult


class CompleteExamOrchestrator(OrchestratorPort):
    """Orchestrator that wraps and executes the complete exam workflow."""

    def __init__(
        self,
        complete_exam_use_case: CompleteExamUseCase,
    ):
        super().__init__()
        self.complete_exam_use_case = complete_exam_use_case

    async def execute(
        self,
        assessment_id: str,
        initial_activity_id: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> ExamStepResult:
        """Execute the full automated exam lifecycle."""
        self.logger.info(
            "Starting CompleteExamOrchestrator for assessment %s", assessment_id
        )
        result = await self.complete_exam_use_case.execute(
            assessment_id=assessment_id,
            initial_activity_id=initial_activity_id,
            user_agent=user_agent,
        )
        self.logger.info("CompleteExamOrchestrator finished")
        return result

