from abc import ABC, abstractmethod
from typing import List, Optional

from Resolucion_script_rosseta.dominio.entities.exam import ExamAnswer, ExamStepResult


class IExamApiPort(ABC):
    """Port for communicating with the Rosetta Stone exam/assessment API."""

    @abstractmethod
    async def submit_step(
        self,
        assessment_id: str,
        activity_id: Optional[str] = None,
        answers: Optional[List[ExamAnswer]] = None,
        user_agent: Optional[str] = None,
        screen_width: int = 1378,
        screen_height: int = 1181,
    ) -> ExamStepResult:
        """Submit answers for an activity step and receive the next step or final score.

        Args:
            assessment_id: The ID of the assessment/screener test.
            activity_id: The current activity being answered.
            answers: List of chosen answers.
            user_agent: Browser User-Agent header string.
            screen_width: Client screen width.
            screen_height: Client screen height.

        Returns:
            ExamStepResult containing the next activity, progress, and/or final score.
        """
        pass

