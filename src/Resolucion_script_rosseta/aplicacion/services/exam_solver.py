import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Resolucion_script_rosseta.dominio.entities.exam import (
    ExamActivity,
    ExamAnswer,
    ExamOption,
    ExamStep,
)
from Resolucion_script_rosseta.dominio.errors import ExamAnswerUnavailable
from Resolucion_script_rosseta.infraestructura.core.base_dir import get_base_dir
from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin


class ExamSolver(LoggingMixin):
    """Solves Rosetta Stone exam activities by choosing the best answer for each step."""

    def __init__(
        self,
        custom_answers_path: Optional[Path] = None,
        allow_fallback: bool = True,
        diagnostics_dir: Optional[Path] = None,
    ):
        self._verified_answers: Dict[str, str] = {}
        self.allow_fallback = allow_fallback
        self.diagnostics_dir = diagnostics_dir or (get_base_dir() / "logs" / "diagnostics")
        self._load_default_verified_answers()
        if custom_answers_path and custom_answers_path.exists():
            self._load_custom_answers(custom_answers_path)

    def _load_default_verified_answers(self) -> None:
        default_file = (
            Path(__file__).parent.parent.parent
            / "infraestructura"
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
            self.logger.info(
                "[ExamSolver] Solved step %s via heuristics: '%s' (%s)",
                step.activity_step_id,
                chosen_opt.text,
                chosen_opt.id,
            )
            return ExamAnswer(
                activity_step_id=step.activity_step_id,
                content_id=chosen_opt.id,
            )

        # 3. Fallback resolution if enabled
        if self.allow_fallback:
            chosen_opt = self._solve_by_fallback(step, activity_type)
            self.logger.warning(
                "[ExamSolver] Question step %s not in verified bank. Using adaptive fallback option '%s' (%s)",
                step.activity_step_id,
                chosen_opt.text or "[audio/visual choice]",
                chosen_opt.id,
            )
            self._dump_unverified_step(step, activity_type, chosen_opt)
            return ExamAnswer(
                activity_step_id=step.activity_step_id,
                content_id=chosen_opt.id,
            )

        # If fallback is explicitly disabled, halt
        raise ExamAnswerUnavailable(step.activity_step_id)

    def _solve_by_heuristics(
        self, step: ExamStep, activity_type: str
    ) -> Optional[ExamOption]:
        """Heuristics to pick the most grammatically/contextually appropriate option."""
        prompt = (step.prompt or "").lower()
        passage = (step.passage_html or "").lower()

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

            # Past / Perfect continuous
            if "all day today" in prompt and text == "have been writing":
                return opt

        # Reading comprehension passage keyword matching
        if passage and step.options:
            best_opt = None
            best_overlap = 0
            for opt in step.options:
                if not opt.text:
                    continue
                words = [w.strip(".,;:?!\"'()") for w in opt.text.lower().split() if len(w) > 3]
                if not words:
                    continue
                overlap = sum(1 for w in words if w in passage)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_opt = opt
            if best_opt and best_overlap >= 2:
                return best_opt

        return None

    def _solve_by_fallback(
        self, step: ExamStep, activity_type: str
    ) -> ExamOption:
        """Selects the best plausible option when no verified answer or heuristic matches."""
        # 1. Prefer option with text over empty/pure audio if available
        text_options = [opt for opt in step.options if opt.text and opt.text.strip()]
        if text_options:
            # Check if any option text has keyword overlap with the prompt
            prompt_words = [
                w.strip(".,;:?!\"'()").lower()
                for w in (step.prompt or "").split()
                if len(w) > 3
            ]
            if prompt_words:
                best_opt = None
                best_score = -1
                for opt in text_options:
                    opt_words = [w.strip(".,;:?!\"'()").lower() for w in opt.text.split()]
                    score = sum(1 for w in opt_words if w in prompt_words)
                    if score > best_score:
                        best_score = score
                        best_opt = opt
                if best_opt and best_score > 0:
                    return best_opt

            # Fallback to the first valid text option
            return text_options[0]

        # 2. If no text options, return the first option
        return step.options[0]

    def _dump_unverified_step(
        self, step: ExamStep, activity_type: str, chosen: ExamOption
    ) -> None:
        """Save unverified step metadata to diagnostics for analysis and curation."""
        if not self.diagnostics_dir:
            return
        try:
            self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
            dump_file = self.diagnostics_dir / "unverified_exam_questions.json"

            existing: List[Dict[str, Any]] = []
            if dump_file.exists():
                try:
                    with open(dump_file, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []

            # Avoid duplicates by step ID
            if not any(item.get("step_id") == step.activity_step_id for item in existing):
                record = {
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "step_id": step.activity_step_id,
                    "activity_type": activity_type,
                    "prompt": step.prompt,
                    "passage": step.passage_html,
                    "options": [
                        {"id": opt.id, "text": opt.text, "audio": opt.audio_uri}
                        for opt in step.options
                    ],
                    "chosen_fallback_id": chosen.id,
                    "chosen_fallback_text": chosen.text,
                }
                existing.append(record)
                with open(dump_file, "w", encoding="utf-8") as f:
                    json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.debug("[ExamSolver] Could not dump unverified question: %s", e)

