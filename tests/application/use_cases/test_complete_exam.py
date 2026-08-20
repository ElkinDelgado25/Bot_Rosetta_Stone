import pytest
from typing import List, Optional

from rosseta_stone_script_a.application.ports.exam_api import IExamApiPort
from rosseta_stone_script_a.application.services.exam_solver import ExamSolver
from rosseta_stone_script_a.application.use_cases.complete_exam import CompleteExamUseCase
from rosseta_stone_script_a.domain.entities.exam import (
    ExamActivity,
    ExamAnswer,
    ExamOption,
    ExamProgress,
    ExamScore,
    ExamStep,
    ExamStepResult,
)


class FakeExamApiAdapter(IExamApiPort):
    """Mock API adapter simulating a sequence of assessment questions ending with testComplete."""

    def __init__(self):
        self.submissions: List[dict] = []
        self.call_count = 0

    async def submit_step(
        self,
        assessment_id: str,
        activity_id: str,
        answers: List[ExamAnswer],
        user_agent: Optional[str] = None,
        screen_width: int = 1378,
        screen_height: int = 1181,
    ) -> ExamStepResult:
        self.call_count += 1
        self.submissions.append({
            "assessment_id": assessment_id,
            "activity_id": activity_id,
            "answers": answers,
        })

        if self.call_count == 1:
            # First submit returned next activity Q2
            return ExamStepResult(
                assessment_name="ScreenerTest",
                form_number=1,
                activity=ExamActivity(
                    activity_id="act_q2",
                    activity_type="RightWordWQuestionWAnswers",
                    steps=[
                        ExamStep(
                            activity_step_id="step_q2",
                            step_type="multipleChoice",
                            prompt="She likes to ____ movies.",
                            options=[
                                ExamOption(id="opt_watch", text="watch"),
                                ExamOption(id="opt_look", text="look"),
                            ],
                        )
                    ],
                ),
                progress=ExamProgress(question_no=2, no_of_questions=2, section=1),
                score=None,
                is_complete=False,
            )
        else:
            # Final submit completed test
            return ExamStepResult(
                assessment_name="testComplete",
                form_number=-1,
                activity=None,
                progress=None,
                score=ExamScore(
                    score=350,
                    max_score=400,
                    cefr="B2",
                    ilr="ILR 2+",
                    clb="CLB 7",
                    warning=None,
                ),
                is_complete=True,
            )


def test_complete_exam_flow(tmp_path):
    import asyncio

    fake_api = FakeExamApiAdapter()
    solver = ExamSolver()
    use_case = CompleteExamUseCase(
        api_port=fake_api,
        solver=solver,
        min_delay_seconds=0.001,
        max_delay_seconds=0.002,
        state_dir=tmp_path,
    )

    result = asyncio.run(
        use_case.execute(
            assessment_id="test_assessment_123",
            initial_activity_id="act_q1",
        )
    )

    assert result.is_complete
    assert result.score is not None
    assert result.score.score == 350
    assert result.score.cefr == "B2"
    assert fake_api.call_count == 2

    # Check persistence
    persisted_file = tmp_path / "exams" / "exam_test_assessment_123.json"
    assert persisted_file.exists()
