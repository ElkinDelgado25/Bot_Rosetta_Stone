"""Fabricates AddProgress messages for Fluency Builder activities.

One message per step, except vocabulary cards: those expand to one message per
carousel word. Answers are derived from the ``correct`` ids the platform itself
ships in the content tree (see docs/FLUENCY_BUILDER.md). Fabrication is clean
for multipleChoice / cloze / grammar-card steps; matching is best-effort from
the correct pairs; writing (free-text) and empty cards submit an attempt.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from Resolucion_script_rosseta.dominio.entities.fluency_activity import FluencyActivity
from Resolucion_script_rosseta.dominio.entities.fluency_sequence import FluencySequence
from Resolucion_script_rosseta.dominio.entities.fluency_step import FluencyStep

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
        self,
        sequence: FluencySequence,
        activity: FluencyActivity,
        next_duration_ms: Optional[Callable[[], int]] = None,
    ) -> List[Dict[str, Any]]:
        """Build the list of step messages for a single activity.

        ``next_duration_ms``, if given, is called once per emitted message
        (one per step, or one per carousel word on a vocabulary card);
        otherwise every message falls back to ``DEFAULT_STEP_DURATION_MS``.
        """
        activity_attempt_id = str(uuid.uuid4())
        messages: List[Dict[str, Any]] = []
        for step in activity.steps:
            if not step.step_id:
                continue
            messages.extend(
                self._messages_for_step(
                    sequence,
                    activity,
                    step,
                    activity_attempt_id,
                    next_duration_ms,
                )
            )
        return messages

    def _messages_for_step(
        self,
        sequence: FluencySequence,
        activity: FluencyActivity,
        step: FluencyStep,
        activity_attempt_id: str,
        next_duration_ms: Optional[Callable[[], int]],
    ) -> List[Dict[str, Any]]:
        def _duration() -> int:
            return next_duration_ms() if next_duration_ms else DEFAULT_STEP_DURATION_MS

        if (step.type or "").lower() == "card" and step.correct_answer_ids:
            # Tarjeta de vocabulario: una palabra por carrusel. El reproductor
            # acredita cada palabra con un answer compuesto ``SS:<id>:1:false``
            # (capturado del tráfico real del reproductor, ver FLUENCY_BUILDER.md);
            # el id suelto de la palabra dejaba la actividad en 1/N.
            return [
                self._build_step_message(
                    sequence,
                    activity,
                    step,
                    activity_attempt_id,
                    _duration(),
                    answers=[{"answer": f"SS:{word_id}:1:false", "correct": True}],
                    score=1,
                )
                for word_id in step.correct_answer_ids
            ]
        return [
            self._build_step_message(
                sequence, activity, step, activity_attempt_id, _duration()
            )
        ]

    def _build_step_message(
        self,
        sequence: FluencySequence,
        activity: FluencyActivity,
        step: FluencyStep,
        activity_attempt_id: str,
        duration_ms: int,
        answers: Optional[List[Dict[str, Any]]] = None,
        score: Optional[int] = None,
    ) -> Dict[str, Any]:
        if answers is None or score is None:
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
            "durationMs": duration_ms,
            "endTimestamp": self._now_iso(),
        }

    def build_usage_overhead_message(
        self,
        sequence: FluencySequence,
        activity: FluencyActivity,
        duration_ms: int,
    ) -> Dict[str, Any]:
        """Build one UsageOverheadMessage for a completed activity.

        Schema captured from the real player (traza de 01-09-2026): the message
        carries **only** these five fields. It is deliberately not shaped like a
        ProgressMessage — there is no ``sequenceId`` and no ``activityId``, and
        the course travels as ``learningContext``. ``id`` is the message's own
        identifier, one per message, not the activity's.
        """
        return {
            "id": str(uuid.uuid4()),
            "userAgent": self.user_agent,
            "learningContext": sequence.course_id,
            "durationMs": duration_ms,
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

