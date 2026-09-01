"""Tests for StoriesSessionCapturer (the player's own usage session id)."""

import json

from rosseta_stone_script_a.application.services.stories_session_capturer import (
    StoriesSessionCapturer,
)

REPORT_URL = "https://lcp.rosettastone.com/api/v3/app_usage/report_usage"


class _Req:
    def __init__(self, url, post_data=None):
        self.url = url
        self.post_data = post_data


class TestStoriesSessionCapturer:
    def test_captures_the_players_session_identifier(self):
        cap = StoriesSessionCapturer()
        cap.handle_request(_Req(REPORT_URL, json.dumps({"session_identifier": "js-1"})))
        assert cap.get_session_identifier() == "js-1"

    def test_ignores_other_requests(self):
        cap = StoriesSessionCapturer()
        cap.handle_request(_Req("https://graph.rosettastone.com/graphql", "{}"))
        assert cap.get_session_identifier() is None

    def test_keeps_the_first_session_it_saw(self):
        cap = StoriesSessionCapturer()
        cap.handle_request(_Req(REPORT_URL, json.dumps({"session_identifier": "js-1"})))
        cap.handle_request(_Req(REPORT_URL, json.dumps({"session_identifier": "js-2"})))
        assert cap.get_session_identifier() == "js-1"

    def test_a_body_without_the_field_captures_nothing(self):
        cap = StoriesSessionCapturer()
        cap.handle_request(_Req(REPORT_URL, json.dumps({"usage_length": 60})))
        assert cap.get_session_identifier() is None

    def test_an_unreadable_body_is_not_an_error(self):
        cap = StoriesSessionCapturer()
        cap.handle_request(_Req(REPORT_URL, "no-json"))
        cap.handle_request(_Req(REPORT_URL, None))
        assert cap.get_session_identifier() is None
