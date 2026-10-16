"""Tests for the read-only Fluency pending checker."""

import asyncio

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    fluency_activity_key,
)
from Resolucion_script_rosseta.aplicacion.orchestrators.fluency_pending_orchestrator import (
    FluencyPendingOrchestrator,
)
from Resolucion_script_rosseta.dominio.entities.fluency_catalog import FluencyCatalog
from Resolucion_script_rosseta.dominio.entities.fluency_course import (
    FluencyCourse,
    FluencySequenceRef,
)
from Resolucion_script_rosseta.infraestructura.state import RunProgressState


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


class _GapApi(_ProgressApi):
    """12 activities listed complete, countOfActivities=13, tree activity omitted."""

    async def get_sequence(self, authorization, course_id, sequence_id, locale=None):
        from Resolucion_script_rosseta.dominio.entities.fluency_activity import (
            FluencyActivity,
        )
        from Resolucion_script_rosseta.dominio.entities.fluency_sequence import (
            FluencySequence,
        )
        from Resolucion_script_rosseta.dominio.entities.fluency_step import FluencyStep

        return FluencySequence(
            sequence_id=sequence_id,
            course_id=course_id,
            title="Lesson 1",
            version=1,
            activities=[
                FluencyActivity(
                    "tree-omitted",
                    "DialogueExpressionWithoutReco",
                    "practice",
                    "tree",
                    [FluencyStep("s1", "select", ["opt"])],
                ),
                FluencyActivity("done-outside", "Vocabulary", "practice", "fixed", []),
            ],
        )

    async def get_progress(self, authorization, course_id):
        return [{
            "courseId": course_id,
            "sequences": [{
                "sequenceId": "lesson-1",
                "percentComplete": 1.0,
                "countOfActivities": 13,
                "activities": [
                    {"activityId": "done-outside", "percentComplete": 1.0},
                    *[
                        {"activityId": f"ok-{i}", "percentComplete": 1.0}
                        for i in range(11)
                    ],
                ],
            }],
        }]


def test_omitted_tree_activities_show_as_pending(tmp_path):
    report = asyncio.run(
        FluencyPendingOrchestrator(_GapApi(), tmp_path).execute(
            {"authorization": "Bearer x", "user_id": "user-1"}
        )
    )
    pending_ids = [item["activity_id"] for item in report["pending"]]
    assert "tree-omitted" in pending_ids
    assert "done-outside" not in pending_ids

