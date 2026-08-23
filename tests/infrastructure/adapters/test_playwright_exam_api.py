import asyncio
import json

from rosseta_stone_script_a.domain.entities.exam import ExamAnswer
from rosseta_stone_script_a.infrastructure.adapters.exam_api.playwright_exam_api import (
    PlaywrightExamApiAdapter,
)


class _Response:
    ok = True
    status = 200

    async def json(self):
        return {
            "data": {
                "assessmentStep": {
                    "assessmentName": "testComplete",
                    "formNumber": -1,
                    "activity": None,
                    "progress": None,
                    "score": {
                        "score": 200,
                        "maxScore": 400,
                        "cefr": "A2",
                    },
                }
            }
        }


class _RequestContext:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()


def _message_for(context):
    return json.loads(context.calls[-1][1]["data"])["variables"]["message"]


def test_bootstrap_request_omits_activity_and_answers():
    context = _RequestContext()
    adapter = PlaywrightExamApiAdapter(context)

    asyncio.run(adapter.submit_step(assessment_id="123"))

    message = _message_for(context)
    assert message["assessmentId"] == "123"
    assert "activityId" not in message
    assert "answers" not in message


def test_information_activity_omits_empty_answers_like_har():
    context = _RequestContext()
    adapter = PlaywrightExamApiAdapter(context)

    asyncio.run(adapter.submit_step(assessment_id="123", activity_id="info", answers=[]))

    message = _message_for(context)
    assert message["activityId"] == "info"
    assert "answers" not in message


def test_answer_payload_matches_har_shape():
    context = _RequestContext()
    adapter = PlaywrightExamApiAdapter(context)

    asyncio.run(
        adapter.submit_step(
            assessment_id="123",
            activity_id="activity-1",
            answers=[ExamAnswer(activity_step_id="step-1", content_id="choice-1")],
        )
    )

    message = _message_for(context)
    assert message["answers"] == [
        {"activityStepId": "step-1", "contentId": "choice-1"}
    ]
