import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from playwright.async_api import APIRequestContext

from rosseta_stone_script_a.application.ports.fluency_api import FluencyApiPort
from rosseta_stone_script_a.domain.entities.fluency_catalog import FluencyCatalog
from rosseta_stone_script_a.domain.entities.fluency_sequence import FluencySequence
from rosseta_stone_script_a.domain.values.fluency_progress_result import (
    FluencyProgressResult,
)
from rosseta_stone_script_a.infrastructure.adapters.fluency_api.fluency_catalog_parser import (
    FluencyCatalogParser,
)
from rosseta_stone_script_a.infrastructure.adapters.fluency_api.fluency_sequence_parser import (
    FluencySequenceParser,
)
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin

GAIA_GRAPHQL_URL = "https://gaia-server.rosettastone.com/graphql"

CATALOG_QUERY = """
query getCoursesAndProgress($locale: String) {
  assignedCourses {
    id
    courseId
    productId
    learningLanguage
    title(locale: $locale)
    cefr
    topics {
      localizations { locale text }
    }
    sequences {
      id
      title(locale: $locale)
    }
  }
  progress {
    id
    courseId
    countOfSequencesInCourse
    sequences { id percentComplete }
  }
}
"""

SEQUENCE_QUERY = """
query getSequence($courseId: String!, $sequenceId: String, $locale: String) {
  sequence(courseId: $courseId, sequenceId: $sequenceId, locale: $locale) {
    id
    sequenceId
    title(locale: $locale)
    version
    activities
  }
}
"""

ADD_PROGRESS_MUTATION = """
mutation AddProgress($userId: String, $messages: [ProgressMessage!]!) {
  progress(userId: $userId, messages: $messages) {
    id
    __typename
  }
}
"""

# Capturada del reproductor real (traza de 01-09-2026, ver
# docs/FLUENCY_BUILDER.md). La versión anterior estaba inferida por analogía con
# AddProgress y era inválida contra el esquema en tres cosas: la variable se
# llama ``$messages`` y no ``$overheads``, no lleva ``userId`` — el usuario sale
# del Bearer — y ``usageOverhead`` devuelve un escalar, así que pedirle
# ``{ id __typename }`` es un error de validación por sí solo.
ADD_USAGE_OVERHEAD_MUTATION = """
mutation AddUsageOverhead($messages: [UsageOverheadMessage!]!) {
  usageOverhead(messages: $messages)
}
"""

GET_PROGRESS_QUERY = """
query getProgress($courseId: String) {
  progress(courseId: $courseId) {
    courseId
    percentComplete
    sequences {
      sequenceId
      percentComplete
      bestGrade
      countOfActivities
      activities {
        activityId
        percentComplete
        bestGrade
        attempts { activityAttemptId }
      }
    }
  }
}
"""


class PlaywrightFluencyApiAdapter(FluencyApiPort, LoggingMixin):
    """Read adapter for the Fluency Builder API (gaia-server) via Playwright.

    Auth: if ``authorization`` is provided it is sent as a header; otherwise the
    request relies on cookies carried by the request context (see FLUENCY_BUILDER.md,
    "Nota de auth" — Bearer vs cookie is confirmed in the write phase).
    """

    def __init__(
        self,
        request_context: APIRequestContext,
        diagnostics_dir: Path | None = None,
    ):
        self.request_context = request_context
        self.diagnostics_dir = diagnostics_dir or Path("logs/diagnostics")

    def _headers(self, authorization: Optional[str]) -> Dict[str, str]:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "content-type": "application/json",
            "origin": "https://learn.rosettastone.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }
        if authorization:
            headers["authorization"] = authorization
        return headers

    async def _post(
        self, operation: str, query: str, variables: Dict[str, Any], authorization: str
    ) -> Dict[str, Any]:
        payload = {
            "operationName": operation,
            "variables": variables,
            "query": query,
        }
        self.logger.info(f"Fluency GraphQL {operation} variables={variables}")
        response = await self.request_context.post(
            GAIA_GRAPHQL_URL, headers=self._headers(authorization), data=payload
        )

        if not response.ok:
            body = await response.text()
            self.logger.error(f"Fluency {operation} failed: {response.status} - {body}")
            raise Exception(f"Fluency {operation} failed: {response.status}")

        data = await response.json()
        if data.get("errors"):
            self.logger.error(f"Fluency {operation} GraphQL errors: {data['errors']}")
            raise Exception(f"Fluency {operation} returned GraphQL errors")

        self._dump(data, operation)
        return data

    async def get_catalog(
        self, authorization: str, locale: Optional[str] = None
    ) -> FluencyCatalog:
        data = await self._post(
            "getCoursesAndProgress",
            CATALOG_QUERY,
            {"locale": locale},
            authorization,
        )
        return FluencyCatalogParser.parse(data, locale=locale)

    async def get_sequence(
        self,
        authorization: str,
        course_id: str,
        sequence_id: str,
        locale: Optional[str] = None,
    ) -> FluencySequence:
        data = await self._post(
            "getSequence",
            SEQUENCE_QUERY,
            {"courseId": course_id, "sequenceId": sequence_id, "locale": locale},
            authorization,
        )
        return FluencySequenceParser.parse(data, course_id=course_id)

    async def add_progress(
        self,
        authorization: str,
        user_id,
        messages,
    ) -> FluencyProgressResult:
        activity_id = messages[0].get("activityId", "") if messages else ""
        course_id = messages[0].get("courseId", "") if messages else ""
        sequence_id = messages[0].get("sequenceId", "") if messages else ""

        payload = {
            "operationName": "AddProgress",
            "variables": {"userId": user_id, "messages": messages},
            "query": ADD_PROGRESS_MUTATION,
        }
        self.logger.info(
            f"AddProgress activity={activity_id} messages={len(messages)}"
        )
        try:
            response = await self.request_context.post(
                GAIA_GRAPHQL_URL, headers=self._headers(authorization), data=payload
            )
        except Exception as exc:
            self.logger.error(f"AddProgress request error: {exc}")
            return FluencyProgressResult(
                success=False,
                status=0,
                course_id=course_id,
                sequence_id=sequence_id,
                activity_id=activity_id,
                message_count=len(messages),
                error=str(exc),
            )

        body = await response.text()
        if not response.ok:
            self.logger.error(f"AddProgress failed: {response.status} - {body}")
            return FluencyProgressResult(
                success=False,
                status=response.status,
                course_id=course_id,
                sequence_id=sequence_id,
                activity_id=activity_id,
                message_count=len(messages),
                response_body=body,
            )

        data = await response.json()
        if data.get("errors"):
            errors_text = str(data["errors"]).lower()
            rate_limited = "rate limit" in errors_text
            if not rate_limited:
                self.logger.error(f"AddProgress GraphQL errors: {data['errors']}")
            return FluencyProgressResult(
                success=False,
                status=response.status,
                course_id=course_id,
                sequence_id=sequence_id,
                activity_id=activity_id,
                message_count=len(messages),
                response_body=body,
                rate_limited=rate_limited,
            )

        return FluencyProgressResult(
            success=True,
            status=response.status,
            course_id=course_id,
            sequence_id=sequence_id,
            activity_id=activity_id,
            message_count=len(messages),
            response_body=body,
        )

    async def add_usage_overhead(
        self,
        authorization: str,
        user_id,
        messages,
    ) -> FluencyProgressResult:
        # UsageOverheadMessage no lleva actividad ni secuencia: el curso viaja
        # como ``learningContext`` y es lo único identificable que hay.
        activity_id = ""
        course_id = messages[0].get("learningContext", "") if messages else ""
        sequence_id = ""

        payload = {
            "operationName": "AddUsageOverhead",
            "variables": {"messages": messages},
            "query": ADD_USAGE_OVERHEAD_MUTATION,
        }
        self.logger.info(
            f"AddUsageOverhead course={course_id} messages={len(messages)}"
        )
        try:
            response = await self.request_context.post(
                GAIA_GRAPHQL_URL, headers=self._headers(authorization), data=payload
            )
        except Exception as exc:
            self.logger.warning(f"AddUsageOverhead request error: {exc}")
            return FluencyProgressResult(
                success=False,
                status=0,
                course_id=course_id,
                sequence_id=sequence_id,
                activity_id=activity_id,
                message_count=len(messages),
                error=str(exc),
            )

        body = await response.text()
        if not response.ok:
            self.logger.warning(f"AddUsageOverhead failed: {response.status} - {body}")
            return FluencyProgressResult(
                success=False,
                status=response.status,
                course_id=course_id,
                sequence_id=sequence_id,
                activity_id=activity_id,
                message_count=len(messages),
                response_body=body,
            )

        data = await response.json()
        if data.get("errors"):
            # Inferred mutation: a schema error here just confirms the guessed
            # shape is wrong, not that anything is broken. Log at info, not
            # error, so it does not read as a failure of the real write path.
            self.logger.info(f"AddUsageOverhead GraphQL errors: {data['errors']}")
            return FluencyProgressResult(
                success=False,
                status=response.status,
                course_id=course_id,
                sequence_id=sequence_id,
                activity_id=activity_id,
                message_count=len(messages),
                response_body=body,
            )

        return FluencyProgressResult(
            success=True,
            status=response.status,
            course_id=course_id,
            sequence_id=sequence_id,
            activity_id=activity_id,
            message_count=len(messages),
            response_body=body,
        )

    async def get_progress(self, authorization: str, course_id: str):
        data = await self._post(
            "getProgress", GET_PROGRESS_QUERY, {"courseId": course_id}, authorization
        )
        return (data.get("data") or {}).get("progress") or []

    def _dump(self, data: dict, operation: str) -> None:
        """Write the raw GraphQL response for diagnostic inspection."""
        try:
            self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            file_path = self.diagnostics_dir / f"fluency_{operation}_{timestamp}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Dumped raw {operation} response to {file_path}")
        except Exception as exc:
            self.logger.warning(f"Could not dump {operation} response: {exc}")
