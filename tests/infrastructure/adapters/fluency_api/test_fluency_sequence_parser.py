"""Tests for FluencySequenceParser.

Fixtures mirror the real getSequence shape from the HAR: ``activities`` is a JSON
scalar (list or JSON-encoded string), each step carries a ``correct`` list of
answer ids, and read-only card steps have no ``correct`` field.
"""

import json

from Resolucion_script_rosseta.infraestructura.adapters.fluency_api.fluency_sequence_parser import (
    FluencySequenceParser,
)

_ACTIVITIES = [
    {
        "activityId": "act-mc",
        "activityType": "DialogueExpressionWithReco",
        "ordering": "tree",
        "interaction": "practice",
        "steps": [
            {
                "activityStepId": "step-1",
                "type": "multipleChoice",
                "correct": ["opt-a", "opt-b", "opt-c"],
            },
            {
                "activityStepId": "step-2",
                "type": "multipleChoice",
                "correct": ["opt-d"],
            },
        ],
    },
    {
        "activityId": "act-card",
        "activityType": "KeyVocabulary",
        "ordering": "tree",
        "interaction": "learn",
        "steps": [
            {"activityStepId": "step-card", "type": "card"}  # no 'correct'
        ],
    },
]


def _response(activities):
    return {
        "data": {
            "sequence": {
                "id": "seq-uuid",
                "sequenceId": "seq-uuid",
                "title": "Window-Shopping (All Skills)",
                "version": 1,
                "activities": activities,
            }
        }
    }


class TestFluencySequenceParser:
    def test_sequence_scalar_fields(self):
        seq = FluencySequenceParser.parse(_response(_ACTIVITIES), course_id="c1")
        assert seq.sequence_id == "seq-uuid"
        assert seq.course_id == "c1"
        assert seq.title == "Window-Shopping (All Skills)"
        assert seq.version == 1

    def test_parses_activities_and_steps(self):
        seq = FluencySequenceParser.parse(_response(_ACTIVITIES), course_id="c1")
        assert [a.activity_id for a in seq.activities] == ["act-mc", "act-card"]
        assert len(seq.activities[0].steps) == 2
        assert seq.activities[0].activity_type == "DialogueExpressionWithReco"

    def test_correct_answer_ids_preserved(self):
        seq = FluencySequenceParser.parse(_response(_ACTIVITIES), course_id="c1")
        step1 = seq.activities[0].steps[0]
        assert step1.correct_answer_ids == ["opt-a", "opt-b", "opt-c"]

    def test_card_step_has_empty_correct(self):
        seq = FluencySequenceParser.parse(_response(_ACTIVITIES), course_id="c1")
        card_step = seq.activities[1].steps[0]
        assert card_step.type == "card"
        assert card_step.correct_answer_ids == []

    def test_activities_as_json_string(self):
        """The scalar may arrive JSON-encoded rather than pre-decoded."""
        encoded = json.dumps(_ACTIVITIES)
        seq = FluencySequenceParser.parse(_response(encoded), course_id="c1")
        assert len(seq.activities) == 2
        assert seq.activities[0].steps[0].correct_answer_ids == ["opt-a", "opt-b", "opt-c"]

    def test_missing_activities_yields_empty_list(self):
        seq = FluencySequenceParser.parse(_response(None), course_id="c1")
        assert seq.activities == []

    def test_malformed_activities_string_is_tolerated(self):
        seq = FluencySequenceParser.parse(_response("{not json"), course_id="c1")
        assert seq.activities == []

    def test_correct_as_bare_string_is_wrapped(self):
        acts = [
            {
                "activityId": "a",
                "activityType": "cloze",
                "ordering": "tree",
                "interaction": "practice",
                "steps": [
                    {"activityStepId": "s", "type": "cloze", "correct": "single-id"}
                ],
            }
        ]
        seq = FluencySequenceParser.parse(_response(acts), course_id="c1")
        assert seq.activities[0].steps[0].correct_answer_ids == ["single-id"]

