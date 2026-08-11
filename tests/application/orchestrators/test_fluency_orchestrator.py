"""Tests for the read-only FluencyOrchestrator, driven without pytest-asyncio."""

import asyncio

from rosseta_stone_script_a.application.orchestrators.fluency_orchestrator import (
    FluencyOrchestrator,
)
from rosseta_stone_script_a.domain.entities.fluency_activity import FluencyActivity
from rosseta_stone_script_a.domain.entities.fluency_catalog import FluencyCatalog
from rosseta_stone_script_a.domain.entities.fluency_course import (
    FluencyCourse,
    FluencySequenceRef,
)
from rosseta_stone_script_a.domain.entities.fluency_sequence import FluencySequence
from rosseta_stone_script_a.domain.entities.fluency_step import FluencyStep


class _FakeApi:
    def __init__(self, catalog):
        self._catalog = catalog
        self.get_sequence_calls = []

    async def get_catalog(self, authorization, locale=None):
        return self._catalog

    async def get_sequence(self, authorization, course_id, sequence_id, locale=None):
        self.get_sequence_calls.append((course_id, sequence_id))
        return FluencySequence(
            sequence_id=sequence_id,
            course_id=course_id,
            title="Lesson",
            version=1,
            activities=[
                FluencyActivity(
                    activity_id="a1",
                    activity_type="mc",
                    interaction="practice",
                    ordering="tree",
                    steps=[FluencyStep(step_id="s1", type="multipleChoice",
                                       correct_answer_ids=["opt-1"])],
                )
            ],
        )


def _catalog(pending=True):
    seqs = [
        FluencySequenceRef("done-seq", "Done", percent_complete=1.0),
        FluencySequenceRef("pend-seq", "Pending", percent_complete=0.0 if pending else 1.0),
    ]
    return FluencyCatalog(
        courses=[
            FluencyCourse("c1", "product.x", "All Skills (B1)", "B1", "Everyday", seqs)
        ]
    )


class TestFluencyOrchestrator:
    def test_reads_first_pending_sequence(self):
        api = _FakeApi(_catalog(pending=True))
        orch = FluencyOrchestrator(api_port=api)

        result = asyncio.run(orch.execute({"authorization": "Bearer x"}))

        assert api.get_sequence_calls == [("c1", "pend-seq")]
        assert result.courses[0].course_id == "c1"

    def test_skips_sequence_read_when_all_complete(self):
        api = _FakeApi(_catalog(pending=False))
        orch = FluencyOrchestrator(api_port=api)

        asyncio.run(orch.execute({"authorization": "Bearer x"}))

        assert api.get_sequence_calls == []

    def test_runs_without_authorization(self):
        """Missing auth is tolerated (cookie auth fallback); still reads catalog."""
        api = _FakeApi(_catalog(pending=True))
        orch = FluencyOrchestrator(api_port=api)

        result = asyncio.run(orch.execute({}))

        assert result is not None
        assert api.get_sequence_calls == [("c1", "pend-seq")]
