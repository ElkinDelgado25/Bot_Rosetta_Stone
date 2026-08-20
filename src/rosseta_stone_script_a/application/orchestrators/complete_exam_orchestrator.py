from typing import Any, Dict, Optional

from rosseta_stone_script_a.application.ports.orchestrator import OrchestratorPort
from rosseta_stone_script_a.application.use_cases.complete_exam import CompleteExamUseCase
from rosseta_stone_script_a.domain.entities.exam import ExamStepResult


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
        initial_activity_id: str,
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
