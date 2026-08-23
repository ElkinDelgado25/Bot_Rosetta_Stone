import json
from typing import Any, Dict, List, Optional

from playwright.async_api import APIRequestContext

from rosseta_stone_script_a.application.ports.exam_api import IExamApiPort
from rosseta_stone_script_a.domain.entities.exam import ExamAnswer, ExamStepResult
from rosseta_stone_script_a.domain.errors import RosettaError
from rosseta_stone_script_a.infrastructure.adapters.exam_api.exam_step_parser import (
    ExamStepParser,
)
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin

GAIA_GRAPHQL_URL = "https://gaia-server.rosettastone.com/graphql"

INSERT_ASSESSMENT_STEP_MUTATION = """mutation insertAssessmentStep($message: AssessmentStepInput!) {
  assessmentStep(message: $message) {
    assessmentName
    formNumber
    activity {
      activityId
      activityType
      interaction
      skills
      steps {
        activityStepId
        type
        content
        instructions
        correct
        logits
        __typename
      }
      instructions
      icon
      metadata
      __typename
    }
    score {
      ...ScoreDetails
      __typename
    }
    progress {
      questionNo
      noOfQuestions
      section
      tally
      ability
      standardError
      __typename
    }
    __typename
  }
}

fragment ScoreDetails on Score {
  score
  maxScore
  cefr
  ilr
  clb
  warning
  __typename
}"""


class ExamApiError(RosettaError):
    """Raised when an error occurs during communication with Gaia assessment API."""
    pass


class PlaywrightExamApiAdapter(IExamApiPort, LoggingMixin):
    """Playwright-based adapter for the Gaia GraphQL assessment endpoint."""

    def __init__(
        self,
        request_context: APIRequestContext,
        authorization_header: Optional[str] = None,
        base_url: str = GAIA_GRAPHQL_URL,
    ):
        self.request_context = request_context
        self.authorization_header = authorization_header
        self.base_url = base_url

    async def submit_step(
        self,
        assessment_id: str,
        activity_id: Optional[str] = None,
        answers: Optional[List[ExamAnswer]] = None,
        user_agent: Optional[str] = None,
        screen_width: int = 1378,
        screen_height: int = 1181,
    ) -> ExamStepResult:
        """Submit assessment answers via GraphQL insertAssessmentStep mutation."""
        ua = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )

        message: Dict[str, Any] = {
            "assessmentId": str(assessment_id),
            "userAgent": ua,
            "screenWidth": screen_width,
            "screenHeight": screen_height,
        }
        if activity_id:
            message["activityId"] = str(activity_id)
            if answers:
                message["answers"] = [
                    {"activityStepId": a.activity_step_id, "contentId": a.content_id}
                    for a in answers
                ]

        payload = {
            "operationName": "insertAssessmentStep",
            "variables": {"message": message},
            "query": INSERT_ASSESSMENT_STEP_MUTATION,
        }

        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "*/*",
        }
        if self.authorization_header:
            headers["Authorization"] = self.authorization_header

        self.logger.debug(
            "[ExamApi] Submitting step for activity %s with %d answers",
            activity_id,
            len(answers or []),
        )

        try:
            response = await self.request_context.post(
                self.base_url,
                data=json.dumps(payload),
                headers=headers,
            )
        except Exception as e:
            self.logger.error("[ExamApi] Network error submitting assessment step: %s", e)
            raise ExamApiError(f"Network error in assessment step: {e}") from e

        if not response.ok:
            body = await response.text()
            self.logger.error(
                "[ExamApi] Server error %d: %s", response.status, body[:300]
            )
            raise ExamApiError(f"Assessment API returned status {response.status}: {body[:200]}")

        raw_json = await response.json()
        if "errors" in raw_json and raw_json["errors"]:
            err_msg = json.dumps(raw_json["errors"])
            self.logger.error("[ExamApi] GraphQL errors in response: %s", err_msg[:300])
            raise ExamApiError(f"GraphQL returned errors: {err_msg[:200]}")

        data = raw_json.get("data", {})
        return ExamStepParser.parse_step_response(data)
