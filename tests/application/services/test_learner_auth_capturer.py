"""Tests for LearnerAuthCapturer (async callback for page.on('response'))."""

import asyncio

from rosseta_stone_script_a.application.services.learner_auth_capturer import (
    LearnerAuthCapturer,
)

LOGIN_URL = "https://login.rosettastone.com/api/authentication/login"


class _Resp:
    """Minimal stand-in for a Playwright response."""

    def __init__(self, url, payload=None, raises=None):
        self.url = url
        self._payload = payload
        self._raises = raises

    async def json(self):
        if self._raises:
            raise self._raises
        return self._payload


def _feed(capturer, response):
    asyncio.run(capturer.handle_response(response))


class TestLearnerAuthCapturer:
    def test_captures_token_and_guid_from_login_response(self):
        cap = LearnerAuthCapturer()
        _feed(
            cap,
            _Resp(LOGIN_URL, {"auth_data": {"access_token": "tok-1", "userId": "guid-1"}}),
        )
        assert cap.get_captured_data() == {
            "access_token": "tok-1",
            "user_guid": "guid-1",
        }
        assert cap.is_complete() is True

    def test_ignores_other_urls(self):
        cap = LearnerAuthCapturer()
        _feed(
            cap,
            _Resp(
                "https://graph.rosettastone.com/graphql",
                {"auth_data": {"access_token": "tok", "userId": "guid"}},
            ),
        )
        assert cap.is_complete() is False

    def test_ignores_body_without_auth_data(self):
        cap = LearnerAuthCapturer()
        _feed(cap, _Resp(LOGIN_URL, {"error": "bad credentials"}))
        assert cap.get_captured_data()["access_token"] is None

    def test_ignores_body_that_is_not_an_object(self):
        cap = LearnerAuthCapturer()
        _feed(cap, _Resp(LOGIN_URL, ["nope"]))
        assert cap.is_complete() is False

    def test_a_second_login_does_not_overwrite_the_first(self):
        cap = LearnerAuthCapturer()
        _feed(cap, _Resp(LOGIN_URL, {"auth_data": {"access_token": "a", "userId": "b"}}))
        _feed(cap, _Resp(LOGIN_URL, {"auth_data": {"access_token": "x", "userId": "y"}}))
        assert cap.get_captured_data() == {"access_token": "a", "user_guid": "b"}

    def test_an_unreadable_body_is_not_an_error(self):
        cap = LearnerAuthCapturer()
        _feed(cap, _Resp(LOGIN_URL, raises=ValueError("not json")))
        assert cap.is_complete() is False

    def test_partial_auth_data_is_not_complete(self):
        cap = LearnerAuthCapturer()
        _feed(cap, _Resp(LOGIN_URL, {"auth_data": {"access_token": "solo"}}))
        assert cap.is_complete() is False
