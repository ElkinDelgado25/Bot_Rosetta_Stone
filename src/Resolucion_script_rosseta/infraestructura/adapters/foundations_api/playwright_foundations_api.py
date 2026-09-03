import json
from datetime import datetime
from pathlib import Path

from playwright.async_api import APIRequestContext

from Resolucion_script_rosseta.aplicacion.ports.foundations_api import FoundationsApiPort
from Resolucion_script_rosseta.dominio.entities.course_menu import CourseMenu
from Resolucion_script_rosseta.dominio.values.path_score_result import PathScoreResult
from Resolucion_script_rosseta.infraestructura.adapters.foundations_api.course_menu_parser import (
    CourseMenuParser,
)
from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin


class PlaywrightFoundationsApiAdapter(FoundationsApiPort, LoggingMixin):
    """Adapter for Foundations API using Playwright's APIRequestContext."""

    def __init__(
        self,
        request_context: APIRequestContext,
        diagnostics_dir: Path | None = None,
    ):
        self.request_context = request_context
        self.diagnostics_dir = diagnostics_dir or Path("logs/diagnostics")

    async def get_course_menu(
        self, authorization: str, language_code: str
    ) -> CourseMenu:
        url = "https://graph.rosettastone.com/graphql"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "content-type": "application/json",
            "authorization": authorization,
            "x-request-id": "66a4813c-8077-4509-9875-6c10608b9933",
            "Referer": "https://totale.rosettastone.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

        query = """
        query GetCourseMenu($languageCode: String!, $filter: String!, $includeMilestoneInLessonFour: Boolean!, $chunking: Boolean!) {
          courseMenu(
            languageCode: $languageCode
            includeMilestoneInLessonFour: $includeMilestoneInLessonFour
            chunking: $chunking
            filter: $filter
          ) {
            currentCourseId
            units {
              id
              index
              unitNumber
              lessons {
                id
                index
                lessonNumber
                paths {
                  unitIndex
                  lessonIndex
                  curriculumLessonIndex
                  type
                  course
                  timeEstimate
                  numChallenges
                  complete
                  percentComplete
                }
              }
            }
          }
        }
        """

        variables = {
            "languageCode": language_code,
            "filter": "ALL",
            "chunking": False,
            "includeMilestoneInLessonFour": True,
        }

        payload = {
            "operationName": "GetCourseMenu",
            "variables": variables,
            "query": query,
        }

        self.logger.info(f"Fetching course menu for language: {language_code}")
        response = await self.request_context.post(url, headers=headers, data=payload)

        if not response.ok:
            self.logger.error(
                f"Failed to fetch course menu: {response.status} - {await response.text()}"
            )
            raise Exception(f"Failed to fetch course menu: {response.status}")

        data = await response.json()
        self._dump_course_menu_response(data, language_code)
        return CourseMenuParser.parse(data)

    def _dump_course_menu_response(self, data: dict, language_code: str) -> None:
        """Write the raw GraphQL course menu response for diagnostic inspection."""
        try:
            self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = (
                self.diagnostics_dir / f"course_menu_{language_code}_{timestamp}.json"
            )
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"Dumped raw course menu response to {file_path}")
        except Exception as exc:
            self.logger.warning(f"Could not dump course menu response: {exc}")

    async def update_path_score(
        self,
        session_token: str,
        school_id: str,
        user_id: str,
        course: str,
        unit_index: int,
        lesson_index: int,
        path_type: str,
        score_correct: int,
        score_incorrect: int,
        duration_ms: int,
        timestamp_ms: int,
        num_challenges: int,
    ) -> PathScoreResult:
        url = f"https://tracking.rosettastone.com/ee/ce/{school_id}/users/{user_id}/path_scores"

        params = {
            "course": course,
            "unit_index": unit_index,
            "lesson_index": lesson_index,
            "path_type": path_type,
            "occurrence": "1",
            "_method": "put",
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "content-type": "text/xml",
            "x-rosettastone-app-version": "ZoomCourse/11.11.2",
            "x-rosettastone-protocol-version": "8",
            "x-rosettastone-session-token": session_token,
            "Referer": "https://totale.rosettastone.com/",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-site",
        }

        body = f"""<path_score>
    <course>{course}</course>
    <unit_index>{unit_index}</unit_index>
    <lesson_index>{lesson_index}</lesson_index>
    <path_type>{path_type}</path_type>
    <occurrence>1</occurrence>
    <complete>true</complete>
    <score_correct>{score_correct}</score_correct>
    <score_incorrect>{score_incorrect}</score_incorrect>
    <score_skipped type="fmcp">0</score_skipped>
    <number_of_challenges>{num_challenges}</number_of_challenges>
    <delta_time>{duration_ms}</delta_time>
    <version>185054</version>
    <updated_at>{timestamp_ms}</updated_at>
    <is_lagged_review_path>false</is_lagged_review_path>
</path_score>"""

        self.logger.debug(
            f"Updating path score: {course} U{unit_index} L{lesson_index} {path_type}"
        )

        try:
            response = await self.request_context.post(
                url, params=params, headers=headers, data=body
            )
        except Exception as exc:
            self.logger.error(
                f"Exception updating path score {course} U{unit_index} L{lesson_index} {path_type}: {exc}"
            )
            return PathScoreResult(
                success=False,
                status=0,
                course=course,
                unit_index=unit_index,
                lesson_index=lesson_index,
                path_type=path_type,
                error=str(exc),
            )

        body_text = ""
        try:
            body_text = await response.text()
        except Exception:
            body_text = "<could not read body>"

        if not response.ok:
            self.logger.error(
                f"Failed path_score {course} U{unit_index} L{lesson_index} {path_type}: {response.status} - {body_text}"
            )
            return PathScoreResult(
                success=False,
                status=response.status,
                course=course,
                unit_index=unit_index,
                lesson_index=lesson_index,
                path_type=path_type,
                response_body=body_text,
            )

        self.logger.info(
            f"Successfully updated path: {course} U{unit_index} L{lesson_index} {path_type}"
        )
        return PathScoreResult(
            success=True,
            status=response.status,
            course=course,
            unit_index=unit_index,
            lesson_index=lesson_index,
            path_type=path_type,
            response_body=body_text,
        )

