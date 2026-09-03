"""Tests for FluencySessionCapturer (sync callback for page.on('request'))."""

from Resolucion_script_rosseta.aplicacion.services.fluency_session_capturer import (
    FluencySessionCapturer,
)


class _Req:
    def __init__(self, url, headers=None, post_data=None):
        self.url = url
        self.headers = headers or {}
        self.post_data = post_data


class TestFluencySessionCapturer:
    def test_captures_authorization_from_gaia(self):
        cap = FluencySessionCapturer()
        cap.handle_request(
            _Req(
                "https://gaia-server.rosettastone.com/graphql",
                headers={"authorization": "Bearer eyJabc"},
            )
        )
        assert cap.get_captured_data()["authorization"] == "Bearer eyJabc"
        assert cap.is_complete() is True

    def test_ignores_non_gaia_hosts(self):
        cap = FluencySessionCapturer()
        cap.handle_request(
            _Req(
                "https://translate.googleapis.com/x",
                headers={"authorization": "Bearer nope"},
            )
        )
        assert cap.get_captured_data()["authorization"] is None
        assert cap.is_complete() is False

    def test_first_authorization_wins(self):
        cap = FluencySessionCapturer()
        base = "https://gaia-server.rosettastone.com/graphql"
        cap.handle_request(_Req(base, headers={"authorization": "first"}))
        cap.handle_request(_Req(base, headers={"authorization": "second"}))
        assert cap.get_captured_data()["authorization"] == "first"

    def test_captures_user_id_from_body(self):
        cap = FluencySessionCapturer()
        body = '{"operationName":"AddProgress","variables":{"userId":"uuid-123"}}'
        cap.handle_request(
            _Req("https://gaia-server.rosettastone.com/graphql", post_data=body)
        )
        assert cap.get_captured_data()["user_id"] == "uuid-123"

    def test_malformed_body_does_not_crash(self):
        cap = FluencySessionCapturer()
        cap.handle_request(
            _Req(
                "https://gaia-server.rosettastone.com/graphql",
                post_data='{"userId": broken',
            )
        )
        assert cap.get_captured_data()["user_id"] is None

    def test_exam_capture_requires_authorization_and_assessment_id(self):
        cap = FluencySessionCapturer()
        base = "https://gaia-server.rosettastone.com/graphql"
        cap.handle_request(_Req(base, headers={"authorization": "Bearer token"}))

        assert cap.is_complete() is True
        assert cap.is_exam_complete() is False
        assert cap.get_exam_missing_keys() == ["assessment_id"]

        cap.handle_request(
            _Req(
                base,
                post_data='{"variables":{"message":{"assessmentId":"12345"}}}',
            )
        )
        assert cap.is_exam_complete() is True
        assert cap.get_exam_missing_keys() == []

