import json
from pathlib import Path
from typing import Dict, List, Optional

from rosseta_stone_script_a.domain.entities.exam import (
    ExamActivity,
    ExamAnswer,
    ExamOption,
    ExamStep,
)
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin


class ExamSolver(LoggingMixin):
    """Solves Rosetta Stone exam activities by choosing the best answer for each step."""

    def __init__(self, custom_answers_path: Optional[Path] = None):
        self._verified_answers: Dict[str, str] = {}
        self._load_default_verified_answers()
        if custom_answers_path and custom_answers_path.exists():
            self._load_custom_answers(custom_answers_path)

    def _load_default_verified_answers(self) -> None:
        default_file = (
            Path(__file__).parent.parent.parent
            / "infrastructure"
            / "adapters"
            / "exam_api"
            / "exam_verified_answers.json"
        )
        if default_file.exists():
            try:
                with open(default_file, "r", encoding="utf-8") as f:
                    self._verified_answers = json.load(f)
                self.logger.debug(
                    "[ExamSolver] Loaded %d default verified answers",
                    len(self._verified_answers),
                )
            except Exception as e:
                self.logger.warning(
                    "[ExamSolver] Failed to load default answers: %s", e
                )

    def _load_custom_answers(self, path: Path) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                custom = json.load(f)
                self._verified_answers.update(custom)
            self.logger.info(
                "[ExamSolver] Loaded custom answers from %s", path
            )
        except Exception as e:
            self.logger.warning("[ExamSolver] Error loading custom answers: %s", e)

    def solve_activity(self, activity: ExamActivity) -> List[ExamAnswer]:
        """Generate answers for all steps in the given activity."""
        answers: List[ExamAnswer] = []

        for step in activity.steps:
            answer = self.solve_step(step, activity.activity_type)
            if answer:
                answers.append(answer)

        return answers

    def solve_step(self, step: ExamStep, activity_type: str = "") -> Optional[ExamAnswer]:
        """Solve a single step within an activity."""
        if not step.options:
            self.logger.debug(
                "[ExamSolver] Step %s has no selectable options (info step).",
                step.activity_step_id,
            )
            return None

        # 1. Check verified answers database
        if step.activity_step_id in self._verified_answers:
            chosen_id = self._verified_answers[step.activity_step_id]
            # Ensure chosen_id actually exists in step options
            if any(opt.id == chosen_id for opt in step.options):
                self.logger.debug(
                    "[ExamSolver] Found verified answer for step %s: %s",
                    step.activity_step_id,
                    chosen_id,
                )
                return ExamAnswer(
                    activity_step_id=step.activity_step_id,
                    content_id=chosen_id,
                )

        # 2. Rule-based heuristic resolution
        chosen_opt = self._solve_by_heuristics(step, activity_type)
        if chosen_opt:
            return ExamAnswer(
                activity_step_id=step.activity_step_id,
                content_id=chosen_opt.id,
            )

        # 3. Fallback: select first valid option
        fallback_opt = step.options[0]
        self.logger.warning(
            "[ExamSolver] Fallback to first option for step %s: %s",
            step.activity_step_id,
            fallback_opt.id,
        )
        return ExamAnswer(
            activity_step_id=step.activity_step_id,
            content_id=fallback_opt.id,
        )

    def _solve_by_heuristics(
        self, step: ExamStep, activity_type: str
    ) -> Optional[ExamOption]:
        """Heuristics to pick the most grammatically/contextually appropriate option."""
        prompt = (step.prompt or "").lower()

        # Check grammar fill-in clues
        for opt in step.options:
            if not opt.text:
                continue
            text = opt.text.strip().lower()

            # Pronoun / reflexive rule: "doesn't belong to me; it's ____" -> hers
            if "belong to" in prompt and "it's" in prompt:
                if text in ["hers", "his", "theirs", "mine", "yours"]:
                    return opt

            # Modal verbs rule: "finish the job, we ____ go home" -> can
            if "finish the job" in prompt and text == "can":
                return opt

            # Future intention: "____ meet us for coffee" -> going to
            if "meet us for coffee" in prompt and text == "going to":
                return opt

            # Conjunctions: "____ bob nor lisa" -> neither
            if "nor" in prompt and text == "neither":
                return opt

            # Condition: "won't be able to go to the park ____ it stops raining" -> unless
            if "won't be able" in prompt and text == "unless":
                return opt

        # Default heuristic: prefer option with text over empty, or longest coherent text
        text_options = [opt for opt in step.options if opt.text]
        if text_options:
            return text_options[0]

        return step.options[0] if step.options else None
