import json
from typing import Any, Dict, List, Optional

from rosseta_stone_script_a.domain.entities.fluency_activity import FluencyActivity
from rosseta_stone_script_a.domain.entities.fluency_sequence import FluencySequence
from rosseta_stone_script_a.domain.entities.fluency_step import FluencyStep


class FluencySequenceParser:
    """Parse a ``getSequence`` GraphQL response into a FluencySequence.

    The ``activities`` field is a JSON scalar: it may arrive already decoded as a
    list, or as a JSON-encoded string. Each step carries a ``correct`` list of
    correct-answer ids, absent for read-only card steps.
    """

    @staticmethod
    def parse(data: Dict[str, Any], course_id: str) -> FluencySequence:
        payload = data.get("data", data) or {}
        seq = payload.get("sequence", payload) or {}

        activities = FluencySequenceParser._activities(
            FluencySequenceParser._decode(seq.get("activities"))
        )

        return FluencySequence(
            sequence_id=seq.get("sequenceId") or seq.get("id"),
            course_id=course_id,
            title=FluencySequenceParser._text(seq.get("title")),
            version=seq.get("version"),
            activities=activities,
        )

    @staticmethod
    def _decode(activities: Any) -> List[Dict[str, Any]]:
        if activities is None:
            return []
        if isinstance(activities, str):
            try:
                activities = json.loads(activities)
            except (ValueError, TypeError):
                return []
        return activities if isinstance(activities, list) else []

    @staticmethod
    def _activities(raw: List[Dict[str, Any]]) -> List[FluencyActivity]:
        result: List[FluencyActivity] = []
        for a in raw:
            if not isinstance(a, dict):
                continue
            result.append(
                FluencyActivity(
                    activity_id=a.get("activityId"),
                    activity_type=a.get("activityType"),
                    interaction=a.get("interaction"),
                    ordering=a.get("ordering"),
                    steps=FluencySequenceParser._steps(a.get("steps")),
                )
            )
        return result

    @staticmethod
    def _steps(raw: Any) -> List[FluencyStep]:
        steps: List[FluencyStep] = []
        for s in raw or []:
            if not isinstance(s, dict):
                continue
            steps.append(
                FluencyStep(
                    step_id=s.get("activityStepId"),
                    type=s.get("type"),
                    correct_answer_ids=FluencySequenceParser._correct(s.get("correct")),
                )
            )
        return steps

    @staticmethod
    def _correct(value: Any) -> List[str]:
        if isinstance(value, list):
            return [v for v in value if isinstance(v, str)]
        if isinstance(value, str):
            return [value]
        return []

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None or isinstance(value, str):
            return value
        if isinstance(value, dict):
            return value.get("text")
        return None
