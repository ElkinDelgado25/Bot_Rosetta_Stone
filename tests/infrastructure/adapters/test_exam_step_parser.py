import pytest
from Resolucion_script_rosseta.infraestructura.adapters.exam_api.exam_step_parser import (
    ExamStepParser,
)


def test_parse_right_word_activity():
    raw_data = {
        "assessmentStep": {
            "assessmentName": "ScreenerTest",
            "formNumber": 1,
            "activity": {
                "activityId": "39c46221-1e40-4b0f-bfce-a14536f7a4df",
                "activityType": "RightWordWQuestionWAnswers",
                "interaction": "test",
                "skills": {
                    "FourSkills": {"Primary": "reading", "Secondary": []},
                    "PedSkills": {"Primary": "grammar", "Secondary": []},
                },
                "steps": [
                    {
                        "activityStepId": "ed786919-2b37-4cd6-bb33-91cfdd0942d3",
                        "type": "multipleChoice",
                        "content": [
                            [{"id": "d0adc263", "text": "I ____ like to cook."}],
                            [
                                {"id": "opt1", "text": "don't"},
                                {"id": "opt2", "text": "not"},
                                {"id": "opt3", "text": "no"},
                                {"id": "opt4", "text": "never"},
                            ],
                        ],
                    }
                ],
            },
            "progress": {
                "questionNo": 1,
                "noOfQuestions": 17,
                "section": 1,
                "tally": None,
                "ability": None,
                "standardError": None,
            },
            "score": None,
        }
    }

    result = ExamStepParser.parse_step_response(raw_data)

    assert not result.is_complete
    assert result.assessment_name == "ScreenerTest"
    assert result.form_number == 1
    assert result.activity is not None
    assert result.activity.activity_id == "39c46221-1e40-4b0f-bfce-a14536f7a4df"
    assert result.activity.activity_type == "RightWordWQuestionWAnswers"
    assert len(result.activity.steps) == 1

    step = result.activity.steps[0]
    assert step.activity_step_id == "ed786919-2b37-4cd6-bb33-91cfdd0942d3"
    assert step.prompt == "I ____ like to cook."
    assert len(step.options) == 4
    assert step.options[0].id == "opt1"
    assert step.options[0].text == "don't"

    assert result.progress is not None
    assert result.progress.question_no == 1
    assert result.progress.no_of_questions == 17
    assert result.progress.section == 1


def test_parse_final_completion_score():
    raw_data = {
        "assessmentStep": {
            "assessmentName": "testComplete",
            "formNumber": -1,
            "activity": None,
            "progress": None,
            "score": {
                "score": 380,
                "maxScore": 400,
                "cefr": "C1",
                "ilr": "ILR 3",
                "clb": "CLB8",
                "warning": None,
            },
        }
    }

    result = ExamStepParser.parse_step_response(raw_data)

    assert result.is_complete
    assert result.assessment_name == "testComplete"
    assert result.activity is None
    assert result.score is not None
    assert result.score.score == 380
    assert result.score.max_score == 400
    assert result.score.cefr == "C1"
    assert result.score.ilr == "ILR 3"
    assert result.score.clb == "CLB8"

