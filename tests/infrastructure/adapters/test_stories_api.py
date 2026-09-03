"""Tests for the Stories usage API client (app_usage on lcp)."""

import asyncio

from Resolucion_script_rosseta.infraestructura.adapters.stories_api.playwright_stories_api import (
    APP_IDENTIFIER,
    PlaywrightStoriesApiAdapter,
)


class _Resp:
    def __init__(self, ok=True, status=200):
        self.ok = ok
        self.status = status


class _Ctx:
    def __init__(self, response=None, raises=None):
        self.response = response or _Resp()
        self.raises = raises
        self.calls = []

    async def post(self, url, data=None, headers=None):
        self.calls.append((url, data or {}, headers or {}))
        if self.raises:
            raise self.raises
        return self.response


class TestStoriesApiAdapter:
    def test_opens_a_usage_session_like_the_player_does(self):
        ctx = _Ctx()
        ok = asyncio.run(
            PlaywrightStoriesApiAdapter(ctx).start_usage_session("s-1", "ENG", 420)
        )
        url, body, headers = ctx.calls[0]
        assert ok is True
        assert url.endswith("/report_usage")
        assert body["session_identifier"] == "s-1"
        assert body["app_identifier"] == APP_IDENTIFIER
        assert body["started_ago"] == 420
        assert body["usage_length"] == 0
        assert body["language"] == "ENG"
        # La API mira de dónde viene la llamada.
        assert headers["Origin"] == "https://totale.rosettastone.com"

    def test_a_negative_elapsed_time_is_clamped(self):
        ctx = _Ctx()
        asyncio.run(PlaywrightStoriesApiAdapter(ctx).start_usage_session("s", "ENG", -5))
        assert ctx.calls[0][1]["started_ago"] == 0

    def test_reports_additional_seconds(self):
        ctx = _Ctx()
        ok = asyncio.run(PlaywrightStoriesApiAdapter(ctx).report_usage("s-1", 600))
        url, body, _ = ctx.calls[0]
        assert ok is True
        assert url.endswith("/report_additional_usage")
        assert body == {"usage_length": 600, "session_identifier": "s-1"}

    def test_a_rejected_post_is_reported_as_failure(self):
        ctx = _Ctx(_Resp(ok=False, status=401))
        assert asyncio.run(PlaywrightStoriesApiAdapter(ctx).report_usage("s", 60)) is False

    def test_a_broken_connection_never_raises(self):
        ctx = _Ctx(raises=RuntimeError("sin red"))
        assert asyncio.run(PlaywrightStoriesApiAdapter(ctx).report_usage("s", 60)) is False

