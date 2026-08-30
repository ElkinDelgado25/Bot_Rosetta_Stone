"""Tests for the read-only Fluency pending checker."""

import asyncio

from rosseta_stone_script_a.application.orchestrators.complete_fluency_orchestrator import (
    fluency_activity_key,
)
from rosseta_stone_script_a.application.orchestrators.fluency_pending_orchestrator import (
    FluencyPendingOrchestrator,
)
from rosseta_stone_script_a.domain.entities.fluency_catalog import FluencyCatalog
from rosseta_stone_script_a.domain.entities.fluency_course import (
    FluencyCourse,
    FluencySequenceRef,
)
from rosseta_stone_script_a.infrastructure.state import RunProgressState


class _ProgressApi:
    async def get_catalog(self, authorization, locale=None):
        return FluencyCatalog(
            courses=[
                FluencyCourse(
                    "course-1",
                    "product-1",
                    "B1 course",
                    "B1",
                    None,
                    [FluencySequenceRef("lesson-1", "Lesson 1")],
                )
            ]
        )

    async def get_progress(self, authorization, course_id):
        return [{
            "courseId": course_id,
            "sequences": [{
                "sequenceId": "lesson-1",
                "activities": [
                    {"activityId": "done-outside", "percentComplete": 1.0},
                    {"activityId": "still-pending", "percentComplete": 0.5},
                ],
            }],
        }]


def test_reconciles_remote_completed_activities_without_sending(tmp_path):
    report = asyncio.run(
        FluencyPendingOrchestrator(_ProgressApi(), tmp_path).execute(
            {"authorization": "Bearer x", "user_id": "user-1"}
        )
    )

    assert report["recovered"] == 1
    assert [item["activity_id"] for item in report["completed"]] == ["done-outside"]
    assert [item["activity_id"] for item in report["pending"]] == ["still-pending"]

    state = RunProgressState(tmp_path / "fluency_user-1.json")
    assert state.is_done(fluency_activity_key("course-1", "lesson-1", "done-outside"))
    assert not state.is_done(fluency_activity_key("course-1", "lesson-1", "still-pending"))
    assert state.count_done_today() == 0
