from typing import Any, Dict, Optional

from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin

GAIA_HOST = "gaia-server.rosettastone.com"


class FluencySessionCapturer(LoggingMixin):
    """Capture Fluency Builder session data from live network traffic.

    Fluency Builder talks to ``gaia-server`` (not the Foundations ``tracking.``
    endpoints), so the Foundations capturer never completes for these accounts.
    This one harvests the ``authorization`` header from gaia requests. If gaia
    turns out to authenticate by cookie instead of a Bearer header, the request
    context still carries the cookies, so reads work even when this stays None.
    """

    def __init__(self):
        self.captured_data: Dict[str, Optional[str]] = {
            "authorization": None,
            "user_id": None,
            "assessment_id": None,
        }

    def handle_request(self, request: Any) -> None:
        """Sync callback for page.on("request"). Must not be async (Playwright)."""
        try:
            url = request.url
            if "/assessments/" in url:
                import re
                match = re.search(r"/assessments/(\d+)", url)
                if match and not self.captured_data["assessment_id"]:
                    self.captured_data["assessment_id"] = match.group(1)
                    self.logger.info("[FluencyCapture] Found assessmentId in URL: %s", match.group(1))

            if GAIA_HOST not in url:
                return

            headers = request.headers
            if not self.captured_data["authorization"] and "authorization" in headers:
                self.captured_data["authorization"] = headers["authorization"]
                self.logger.info("[FluencyCapture] Found gaia authorization header")

            # userId travels in the JSON body of some operations (AddProgress,
            # AssignedCourseIds); reads (getCoursesAndProgress) don't need it, so
            # this is best-effort and never required for the reading phase.
            if not self.captured_data["user_id"]:
                self._try_capture_user_id(request)
            if not self.captured_data["assessment_id"]:
                self._try_capture_assessment_id(request)
        except Exception as e:
            self.logger.error(f"Error in Fluency request interceptor: {e}")

    def _try_capture_assessment_id(self, request: Any) -> None:
        try:
            post_data = request.post_data
        except Exception:
            post_data = None
        if not post_data or '"assessmentId"' not in post_data:
            return
        import json
        try:
            payload = json.loads(post_data)
        except (ValueError, TypeError):
            return
        for item in payload if isinstance(payload, list) else [payload]:
            variables = (item or {}).get("variables") if isinstance(item, dict) else None
            msg = (variables or {}).get("message") if variables else None
            assess_id = (msg or {}).get("assessmentId") if msg else (variables or {}).get("assessmentId")
            if assess_id:
                self.captured_data["assessment_id"] = str(assess_id)
                self.logger.info("[FluencyCapture] Found assessmentId: %s", assess_id)
                return

    def _try_capture_user_id(self, request: Any) -> None:
        try:
            post_data = request.post_data
        except Exception:
            post_data = None
        if not post_data or '"userId"' not in post_data:
            return
        import json

        try:
            payload = json.loads(post_data)
        except (ValueError, TypeError):
            return
        for item in payload if isinstance(payload, list) else [payload]:
            variables = (item or {}).get("variables") if isinstance(item, dict) else None
            user_id = (variables or {}).get("userId") if variables else None
            if user_id:
                self.captured_data["user_id"] = user_id
                self.logger.info("[FluencyCapture] Found userId")
                return

    def get_captured_data(self) -> Dict[str, Optional[str]]:
        return self.captured_data

    def is_complete(self) -> bool:
        """The reading phase only needs an authorization token (or cookie auth)."""
        return self.captured_data.get("authorization") is not None

    def is_exam_complete(self) -> bool:
        """An exam needs both Gaia authorization and its captured assessment ID."""
        return all(
            self.captured_data.get(key)
            for key in ("authorization", "assessment_id")
        )

    def get_exam_missing_keys(self) -> list[str]:
        return [
            key
            for key in ("authorization", "assessment_id")
            if not self.captured_data.get(key)
        ]

