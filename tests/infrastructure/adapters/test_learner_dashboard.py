"""Tests for the learner dashboard reader (hours read back from prism)."""

import asyncio

from rosseta_stone_script_a.infrastructure.adapters.learner_dashboard.playwright_learner_dashboard import (
    PlaywrightLearnerDashboardAdapter,
)


class _Resp:
    def __init__(self, payload=None, ok=True, status=200):
        self.ok = ok
        self.status = status
        self._payload = payload

    async def json(self):
        return self._payload


class _Ctx:
    """Stand-in for Playwright's APIRequestContext."""

    def __init__(self, response=None, raises=None):
        self.response = response
        self.raises = raises
        self.calls = []

    async def get(self, url, headers=None):
        self.calls.append((url, headers or {}))
        if self.raises:
            raise self.raises
        return self.response


def _hours(ctx, token="tok", guid="guid"):
    return asyncio.run(PlaywrightLearnerDashboardAdapter(ctx).get_hours(token, guid))


class TestLearnerDashboardAdapter:
    def test_maps_milliseconds_to_hours(self):
        ctx = _Ctx(
            _Resp(
                {
                    "name": "Brithany",
                    "allTimeActivities": {
                        "totalTimeSpentMs": 3_600_000,
                        "elearningTimeSpentMs": 1_800_000,
                    },
                }
            )
        )
        hours = _hours(ctx)
        assert hours.name == "Brithany"
        assert hours.total_hours == 1.0
        assert hours.elearning_hours == 0.5

    def test_sends_bearer_and_guid(self):
        ctx = _Ctx(_Resp({"allTimeActivities": {}}))
        _hours(ctx, token="tok-9", guid="guid-9")
        url, headers = ctx.calls[0]
        assert "guid-9" in url
        assert headers["Authorization"] == "Bearer tok-9"

    def test_missing_credentials_skips_the_request(self):
        ctx = _Ctx(_Resp({}))
        assert _hours(ctx, token="", guid="guid") is None
        assert _hours(ctx, token="tok", guid="") is None
        assert ctx.calls == []

    def test_a_rejected_request_reports_no_hours(self):
        assert _hours(_Ctx(_Resp(None, ok=False, status=403))) is None

    def test_a_failed_request_never_raises(self):
        assert _hours(_Ctx(raises=RuntimeError("network down"))) is None

    def test_a_body_that_is_not_an_object_reports_no_hours(self):
        assert _hours(_Ctx(_Resp(["unexpected"]))) is None

    def test_missing_activity_block_counts_as_zero(self):
        hours = _hours(_Ctx(_Resp({"name": "Sin datos"})))
        assert hours.total_hours == 0.0
        assert hours.elearning_hours == 0.0
