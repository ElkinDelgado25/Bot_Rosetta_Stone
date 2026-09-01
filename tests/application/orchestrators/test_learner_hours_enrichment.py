"""The capture workflow enriches its result with the platform's own hours.

Reading them is a check, never a requirement: without a dashboard, without
credentials or with the dashboard down, the run must come back exactly as it
did before this feature existed.
"""

import asyncio

from rosseta_stone_script_a.application.orchestrators.open_fundations import (
    OpenFundations,
)
from rosseta_stone_script_a.domain.values.learner_hours import LearnerHours


class _Dashboard:
    def __init__(self, hours=None):
        self.hours = hours
        self.calls = []

    async def get_hours(self, access_token, user_guid):
        self.calls.append((access_token, user_guid))
        return self.hours


def _orchestrator(dashboard=None, captured=None):
    orch = OpenFundations(
        login_use_case=None,
        navigate_use_case=None,
        web_session=None,
        session_capturer=None,
        learner_dashboard=dashboard,
    )
    if captured:
        orch.learner_auth_capturer.captured_data.update(captured)
    return orch


def _read(orch):
    return asyncio.run(orch._read_learner_hours())


CREDS = {"access_token": "tok", "user_guid": "guid"}


class TestLearnerHoursEnrichment:
    def test_adds_hours_and_credentials(self):
        dashboard = _Dashboard(LearnerHours("Ana", 12.5, 9.25))
        result = _read(_orchestrator(dashboard, CREDS))
        assert result["hours_total"] == 12.5
        assert result["hours_elearning"] == 9.25
        assert result["access_token"] == "tok"
        assert result["user_guid"] == "guid"
        assert dashboard.calls == [("tok", "guid")]

    def test_without_a_dashboard_only_the_credentials_travel(self):
        result = _read(_orchestrator(None, CREDS))
        assert result == CREDS

    def test_without_credentials_the_dashboard_is_not_called(self):
        dashboard = _Dashboard(LearnerHours("Ana", 1.0, 1.0))
        result = _read(_orchestrator(dashboard))
        assert result == {}
        assert dashboard.calls == []

    def test_an_unreadable_dashboard_leaves_the_run_untouched(self):
        result = _read(_orchestrator(_Dashboard(None), CREDS))
        assert "hours_total" not in result
        assert result == CREDS


class TestLearnerHoursValue:
    def test_ignores_unusable_numbers(self):
        hours = LearnerHours.from_activities(
            "X", {"totalTimeSpentMs": "no-es-un-numero", "elearningTimeSpentMs": None}
        )
        assert hours.total_hours == 0.0
        assert hours.elearning_hours == 0.0
