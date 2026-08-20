import asyncio
import json
import random
from pathlib import Path
from typing import Any, Dict, Optional

from rosseta_stone_script_a.application.ports.exam_api import IExamApiPort
from rosseta_stone_script_a.application.services.exam_solver import ExamSolver
from rosseta_stone_script_a.domain.entities.exam import (
    ExamActivity,
    ExamAnswer,
    ExamScore,
    ExamStepResult,
)
from rosseta_stone_script_a.domain.errors import RosettaError
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin


class CompleteExamUseCase(LoggingMixin):
    """Use case to sequentially solve and complete a Rosetta Stone Screener/Placement exam."""

    def __init__(
        self,
        api_port: IExamApiPort,
        solver: Optional[ExamSolver] = None,
        min_delay_seconds: float = 2.0,
        max_delay_seconds: float = 5.0,
        state_dir: Optional[Path] = None,
        dry_run: bool = False,
    ):
        self.api_port = api_port
        self.solver = solver or ExamSolver()
        self.min_delay_seconds = min_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.state_dir = state_dir
        self.dry_run = dry_run

    async def execute(
        self,
        assessment_id: str,
        initial_activity_id: str,
        user_agent: Optional[str] = None,
    ) -> ExamStepResult:
        """Run the complete assessment loop until test is complete."""
        self.logger.info(
            "Starting automated exam for assessmentId=%s (initialActivityId=%s)",
            assessment_id,
            initial_activity_id,
        )

        current_activity_id = initial_activity_id
        last_result: Optional[ExamStepResult] = None
        step_count = 0
        max_steps = 150  # Safety ceiling

        while step_count < max_steps:
            step_count += 1

            # 1. Determine answers for current activity
            answers: list[ExamAnswer] = []
            if last_result and last_result.activity:
                answers = self.solver.solve_activity(last_result.activity)
                self.logger.info(
                    "[Exam Step #%d] Solving %d steps for activity %s (%s)",
                    step_count,
                    len(answers),
                    current_activity_id,
                    last_result.activity.activity_type,
                )

            # 2. Simulate human reading/answering time
            if step_count > 1 and not self.dry_run:
                delay = random.uniform(self.min_delay_seconds, self.max_delay_seconds)
                self.logger.debug(
                    "[Exam Step #%d] Waiting %.1fs human reading delay...",
                    step_count,
                    delay,
                )
                await asyncio.sleep(delay)

            # 3. Submit step to API
            if self.dry_run:
                self.logger.info(
                    "[DRY RUN] Would submit step %s with %d answers",
                    current_activity_id,
                    len(answers),
                )
                break

            result = await self.api_port.submit_step(
                assessment_id=assessment_id,
                activity_id=current_activity_id,
                answers=answers,
                user_agent=user_agent,
            )
            last_result = result

            # Log progress
            if result.progress:
                p = result.progress
                self.logger.info(
                    "Exam Progress: Section %d, Question %d/%d (total steps executed: %d)",
                    p.section,
                    p.question_no,
                    p.no_of_questions,
                    step_count,
                )

            # Check if exam is completed
            if result.is_complete or result.activity is None:
                self.logger.info("Exam completed successfully!")
                if result.score:
                    s = result.score
                    self.logger.info(
                        "================ EXAM RESULTS ================\n"
                        "  Score: %d/%d\n"
                        "  CEFR Level: %s\n"
                        "  ILR: %s\n"
                        "  CLB: %s\n"
                        "==============================================",
                        s.score,
                        s.max_score,
                        s.cefr,
                        s.ilr or "N/A",
                        s.clb or "N/A",
                    )
                    self._persist_result(assessment_id, result.score)
                return result

            # Set next activity ID for next iteration
            current_activity_id = result.activity.activity_id

        self.logger.warning(
            "Exam loop terminated after %d steps without explicit completion.",
            step_count,
        )
        return last_result or ExamStepResult(
            assessment_name="unknown",
            form_number=-1,
            is_complete=False,
        )

    def _persist_result(self, assessment_id: str, score: ExamScore) -> None:
        """Persist final exam score to state directory."""
        if not self.state_dir:
            return
        try:
            target_dir = self.state_dir / "exams"
            target_dir.mkdir(parents=True, exist_ok=True)
            target_file = target_dir / f"exam_{assessment_id}.json"

            data = {
                "assessment_id": assessment_id,
                "score": score.score,
                "max_score": score.max_score,
                "cefr": score.cefr,
                "ilr": score.ilr,
                "clb": score.clb,
                "warning": score.warning,
            }
            with open(target_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.logger.info("Saved exam result to %s", target_file)
        except Exception as e:
            self.logger.warning("Failed to persist exam result: %s", e)
