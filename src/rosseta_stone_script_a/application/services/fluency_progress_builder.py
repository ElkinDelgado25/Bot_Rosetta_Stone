"""Fabricates AddProgress messages for Fluency Builder activities.

One message per step. Answers are derived from the ``correct`` ids the platform
itself ships in the content tree (see docs/FLUENCY_BUILDER.md). Fabrication is
clean for multipleChoice / cloze / grammar-card steps; matching is best-effort
from the correct pairs; writing (free-text) and vocabulary cards submit an
attempt, which is enough when completion is gated on submission rather than score.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from rosseta_stone_script_a.domain.entities.fluency_activity import FluencyActivity
from rosseta_stone_script_a.domain.entities.fluency_sequence import FluencySequence
from rosseta_stone_script_a.domain.entities.fluency_step import FluencyStep

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)
DEFAULT_STEP_DURATION_MS = 5000


class FluencyProgressBuilder:
    """Build ProgressMessage dicts for a sequence's activities."""

    def __init__(self, user_agent: str = USER_AGENT):
        self.user_agent = user_agent

    def build_activity_messages(
        self, sequence: FluencySequence, activity: FluencyActivity
    ) -> List[Dict[str, Any]]:
        """Build the list of step messages for a single activity."""
        activity_attempt_id = str(uuid.uuid4())
        return [
            self._build_step_message(sequence, activity, step, activity_attempt_id)
            for step in activity.steps
            if step.step_id
        ]

    def _build_step_message(
        self,
        sequence: FluencySequence,
        activity: FluencyActivity,
        step: FluencyStep,
        activity_attempt_id: str,
    ) -> Dict[str, Any]:
        answers, score = self._answers_for(step)
        return {
            "userAgent": self.user_agent,
            "courseId": sequence.course_id,
            "sequenceId": sequence.sequence_id,
            "version": sequence.version if sequence.version is not None else 1,
            "activityId": activity.activity_id,
            "activityAttemptId": activity_attempt_id,
            "activityStepId": step.step_id,
            "activityStepAttemptId": str(uuid.uuid4()),
            "answers": answers,
            "score": score,
            "skip": False,
            "durationMs": DEFAULT_STEP_DURATION_MS,
            "endTimestamp": self._now_iso(),
        }

    def _answers_for(self, step: FluencyStep):
        """Return (answers, score) fabricated for a step, keyed by its type.

        score is an int (1) to match the browser exactly — it sends ``score: 1``,
        not ``1.0``.
        """
        correct = step.correct_answer_ids
        step_type = (step.type or "").lower()

        if not correct:
            # Cards and any answerless step: mark as viewed/complete.
            return [], 1

        if step_type == "cloze":
            # One blank per correct id, placed in its own position -> all correct.
            return [{"answer": cid, "correct": True} for cid in correct], 1

        if step_type == "matching":
            # correct entries are "leftId:rightId" pairs; submit each as a match.
            return [{"answer": pair, "correct": True} for pair in correct], 1

        if step_type == "multiplechoice":
            # Any id in `correct` is an accepted answer for the single choice.
            return [{"answer": correct[0], "correct": True}], 1

        # writing / unknown: best-effort single attempt from the correct pool.
        return [{"answer": correct[0], "correct": True}], 1

    def _now_iso(self) -> str:
        return (
            datetime.now(timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )
