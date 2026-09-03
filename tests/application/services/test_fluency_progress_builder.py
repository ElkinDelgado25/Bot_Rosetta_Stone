"""Tests for FluencyProgressBuilder — message fabrication per step type."""

from Resolucion_script_rosseta.aplicacion.services.fluency_progress_builder import (
    FluencyProgressBuilder,
)
from Resolucion_script_rosseta.dominio.entities.fluency_activity import FluencyActivity
from Resolucion_script_rosseta.dominio.entities.fluency_sequence import FluencySequence
from Resolucion_script_rosseta.dominio.entities.fluency_step import FluencyStep


def _sequence(steps):
    activity = FluencyActivity(
        activity_id="act-1",
        activity_type="Mixed",
        interaction="practice",
        ordering="tree",
        steps=steps,
    )
    return (
        FluencySequence(
            sequence_id="seq-1",
            course_id="course-1",
            title="Lesson",
            version=3,
            activities=[activity],
        ),
        activity,
    )


class TestFluencyProgressBuilder:
    def test_one_message_per_step(self):
        seq, act = _sequence(
            [
                FluencyStep("s1", "multipleChoice", ["a", "b"]),
                FluencyStep("s2", "card", []),
            ]
        )
        msgs = FluencyProgressBuilder().build_activity_messages(seq, act)
        assert len(msgs) == 2
        assert {m["activityStepId"] for m in msgs} == {"s1", "s2"}

    def test_shared_activity_attempt_id_unique_step_attempt_ids(self):
        seq, act = _sequence(
            [FluencyStep("s1", "cloze", ["a"]), FluencyStep("s2", "cloze", ["b"])]
        )
        msgs = FluencyProgressBuilder().build_activity_messages(seq, act)
        assert msgs[0]["activityAttemptId"] == msgs[1]["activityAttemptId"]
        assert msgs[0]["activityStepAttemptId"] != msgs[1]["activityStepAttemptId"]

    def test_carries_sequence_identity_and_version(self):
        seq, act = _sequence([FluencyStep("s1", "card", [])])
        m = FluencyProgressBuilder().build_activity_messages(seq, act)[0]
        assert m["courseId"] == "course-1"
        assert m["sequenceId"] == "seq-1"
        assert m["activityId"] == "act-1"
        assert m["version"] == 3

    def test_multiplechoice_sends_one_correct_id(self):
        seq, act = _sequence([FluencyStep("s1", "multipleChoice", ["x", "y", "z"])])
        m = FluencyProgressBuilder().build_activity_messages(seq, act)[0]
        assert m["answers"] == [{"answer": "x", "correct": True}]
        assert m["score"] == 1

    def test_cloze_maps_each_correct_id_positionally(self):
        seq, act = _sequence([FluencyStep("s1", "cloze", ["a", "b", "c"])])
        m = FluencyProgressBuilder().build_activity_messages(seq, act)[0]
        assert m["answers"] == [
            {"answer": "a", "correct": True},
            {"answer": "b", "correct": True},
            {"answer": "c", "correct": True},
        ]
        assert m["score"] == 1

    def test_matching_sends_each_pair(self):
        seq, act = _sequence([FluencyStep("s1", "matching", ["l1:r1", "l2:r2"])])
        m = FluencyProgressBuilder().build_activity_messages(seq, act)[0]
        assert m["answers"] == [
            {"answer": "l1:r1", "correct": True},
            {"answer": "l2:r2", "correct": True},
        ]

    def test_card_has_empty_answers_and_full_score(self):
        seq, act = _sequence([FluencyStep("s1", "card", [])])
        m = FluencyProgressBuilder().build_activity_messages(seq, act)[0]
        assert m["answers"] == []
        assert m["score"] == 1

    def test_step_without_id_is_skipped(self):
        seq, act = _sequence(
            [FluencyStep(None, "card", []), FluencyStep("s2", "card", [])]
        )
        msgs = FluencyProgressBuilder().build_activity_messages(seq, act)
        assert [m["activityStepId"] for m in msgs] == ["s2"]

    def test_endtimestamp_is_utc_z(self):
        seq, act = _sequence([FluencyStep("s1", "card", [])])
        m = FluencyProgressBuilder().build_activity_messages(seq, act)[0]
        assert m["endTimestamp"].endswith("Z")
        assert m["skip"] is False

    def test_default_duration_is_flat_constant(self):
        seq, act = _sequence([FluencyStep("s1", "card", [])])
        m = FluencyProgressBuilder().build_activity_messages(seq, act)[0]
        assert m["durationMs"] == 5000

    def test_next_duration_ms_is_called_once_per_emitted_step(self):
        seq, act = _sequence(
            [FluencyStep("s1", "card", []), FluencyStep("s2", "card", [])]
        )
        durations = iter([1234, 5678])
        msgs = FluencyProgressBuilder().build_activity_messages(
            seq, act, next_duration_ms=lambda: next(durations)
        )
        assert [m["durationMs"] for m in msgs] == [1234, 5678]

    def test_usage_overhead_message_matches_the_captured_schema(self):
        """Los cinco campos de la traza real, ni uno más.

        ``UsageOverheadMessage`` es un input estricto: colar en él los campos de
        un ProgressMessage (``sequenceId``, ``activityId``) es un error de
        validación, no un campo de más que el servidor ignore.
        """
        seq, act = _sequence([FluencyStep("s1", "card", [])])
        m = FluencyProgressBuilder().build_usage_overhead_message(seq, act, 9000)
        assert set(m) == {
            "id",
            "userAgent",
            "learningContext",
            "durationMs",
            "endTimestamp",
        }
        assert m["learningContext"] == "course-1"
        assert m["durationMs"] == 9000
        assert m["endTimestamp"].endswith("Z")

    def test_each_usage_overhead_message_gets_its_own_id(self):
        seq, act = _sequence([FluencyStep("s1", "card", [])])
        builder = FluencyProgressBuilder()
        first = builder.build_usage_overhead_message(seq, act, 9000)
        second = builder.build_usage_overhead_message(seq, act, 9000)
        assert first["id"] != second["id"]

