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

    def test_card_carousel_words_become_correct_ids(self):
        """Prospective Customer: Vocabulary se quedaba al 6% (1/16).

        getSequence entrega un solo step ``card``; las palabras van en
        ``content[0].carousel``. Sin un AddProgress por wordId el servidor
        cuenta una sola tarjeta vista.
        """
        activities = [
            {
                "activityId": "act-vocab",
                "activityType": "Vocabulary",
                "ordering": "linear",
                "interaction": "learn",
                "steps": [
                    {
                        "activityStepId": "step-card",
                        "type": "card",
                        "content": [
                            {
                                "id": "block-1",
                                "carousel": [
                                    [
                                        {"id": "head-1", "type": "heading"},
                                        {"id": "word-1", "type": "word"},
                                        {"id": "word-2", "type": "word"},
                                    ],
                                    [{"id": "word-3", "type": "word"}],
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
        seq = FluencySequenceParser.parse(_response(activities), course_id="c1")
        assert seq.activities[0].steps[0].correct_answer_ids == [
            "word-1",
            "word-2",
            "word-3",
        ]

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


_CONVERSATION = [
    {
        "activityId": "act-conv",
        "activityType": "DialogueExpressionWithReco",
        "ordering": "tree",
        "interaction": "practice",
        "steps": [
            {
                "activityStepId": "step-free",
                "type": "multipleChoice",
                "correct": ["opt-a", "opt-b", "opt-c"],
                "postProcess": {
                    "successResponses": [
                        {"responseId": "opt-a", "nextStep": "step-tail"},
                        {"responseId": "opt-b", "nextStep": "step-tail"},
                        {"responseId": "opt-c", "nextStep": "step-tail"},
                    ]
                },
                "content": [
                    [
                        {
                            "id": "prompt-1",
                            "contentChunks": [
                                {"text": "Do you often write letters?"}
                            ],
                        },
                        {
                            "id": "opt-a",
                            "contentChunks": [
                                {
                                    "text": "Yes, of course.",
                                    "audios": [
                                        {
                                            "type": "sound_mp3",
                                            "media_uri": "urn:puddle_unencrypted:aaa111",
                                        }
                                    ],
                                }
                            ],
                        },
                        {
                            "id": "opt-b",
                            "contentChunks": [
                                {
                                    "text": "No, sorry.",
                                    "audios": [
                                        {
                                            "type": "sound_mp3",
                                            "media_uri": "urn:puddle_unencrypted:bbb222",
                                        }
                                    ],
                                }
                            ],
                        },
                        {"id": "opt-c", "contentChunks": [{"text": "Maybe."}]},
                    ]
                ],
            },
            {
                "activityStepId": "step-tail",
                "type": "multipleChoice",
                "correct": ["opt-d", "opt-e", "opt-f"],
                "postProcess": {
                    "successResponses": [{"responseId": "opt-f", "nextStep": ""}]
                },
                "content": [
                    [
                        {"id": "opt-d", "contentChunks": [{"text": "Only one."}]},
                        {"id": "opt-e", "contentChunks": [{"text": "Two."}]},
                        {
                            "id": "opt-f",
                            "contentChunks": [
                                {"text": "No, but I"},
                                {
                                    "text": "have enough.",
                                    "audios": [
                                        {
                                            "type": "sound_mp3",
                                            "media_uri": "urn:puddle_unencrypted:fff666",
                                        }
                                    ],
                                },
                            ],
                        },
                    ]
                ],
            },
        ],
    }
]


class TestConversationStepOptions:
    """El paso de cierre acepta una sola respuesta: hay que saber cuál."""

    def _steps(self):
        seq = FluencySequenceParser.parse(_response(_CONVERSATION), course_id="c1")
        return seq.activities[0].steps

    def test_success_answer_ids_from_post_process(self):
        free, tail = self._steps()
        assert free.success_answer_ids == ["opt-a", "opt-b", "opt-c"]
        assert tail.success_answer_ids == ["opt-f"]

    def test_step_without_post_process_has_no_success_ids(self):
        seq = FluencySequenceParser.parse(_response(_ACTIVITIES), course_id="c1")
        assert seq.activities[0].steps[0].success_answer_ids == []

    def test_answers_carry_text_and_audio_sha(self):
        free, _ = self._steps()
        assert [a.id for a in free.answers] == ["opt-a", "opt-b", "opt-c"]
        primero = free.answers[0]
        assert primero.text == "Yes, of course."
        assert primero.audio_sha == "aaa111"

    def test_option_text_joins_content_chunks(self):
        _, tail = self._steps()
        opt_f = next(a for a in tail.answers if a.id == "opt-f")
        assert opt_f.text == "No, but I have enough."
        assert opt_f.audio_sha == "fff666"

    def test_options_without_audio_keep_none_sha(self):
        free, _ = self._steps()
        opt_c = next(a for a in free.answers if a.id == "opt-c")
        assert opt_c.audio_sha is None

    def test_prompt_item_is_not_an_answer(self):
        free, _ = self._steps()
        assert all(a.id != "prompt-1" for a in free.answers)

    def test_success_ids_deduplicated(self):
        acts = [
            {
                "activityId": "a",
                "activityType": "DialogueExpressionWithReco",
                "ordering": "tree",
                "interaction": "practice",
                "steps": [
                    {
                        "activityStepId": "s",
                        "type": "multipleChoice",
                        "correct": ["opt-a"],
                        "postProcess": {
                            "successResponses": [
                                {"responseId": "opt-a", "nextStep": ""},
                                {"responseId": "opt-a", "nextStep": ""},
                            ]
                        },
                    }
                ],
            }
        ]
        seq = FluencySequenceParser.parse(_response(acts), course_id="c1")
        assert seq.activities[0].steps[0].success_answer_ids == ["opt-a"]

    def test_media_uri_without_urn_prefix_kept(self):
        acts = [
            {
                "activityId": "a",
                "activityType": "DialogueExpressionWithReco",
                "ordering": "tree",
                "interaction": "practice",
                "steps": [
                    {
                        "activityStepId": "s",
                        "type": "multipleChoice",
                        "correct": ["opt-a"],
                        "content": [
                            [
                                {
                                    "id": "opt-a",
                                    "contentChunks": [
                                        {
                                            "text": "Yes.",
                                            "audios": [
                                                {"media_uri": "planosha123"}
                                            ],
                                        }
                                    ],
                                }
                            ]
                        ],
                    }
                ],
            }
        ]
        seq = FluencySequenceParser.parse(_response(acts), course_id="c1")
        assert seq.activities[0].steps[0].answers[0].audio_sha == "planosha123"

