"""Tests for CompleteFluencyOrchestrator: limits, dry-run, state, verification."""

import asyncio

import pytest

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    CompleteFluencyOrchestrator,
    fluency_activity_key,
)
from Resolucion_script_rosseta.aplicacion.services.fluency_duration_calculator import (
    FluencyDurationCalculator,
)


@pytest.fixture(autouse=True)
def _no_real_sleep(monkeypatch):
    """Keep the suite fast: never actually sleep for pacing/backoff."""
    async def _instant(*_a, **_k):
        return None

    monkeypatch.setattr(
        "Resolucion_script_rosseta.aplicacion.orchestrators."
        "complete_fluency_orchestrator.asyncio.sleep",
        _instant,
    )
from Resolucion_script_rosseta.dominio.entities.fluency_activity import FluencyActivity
from Resolucion_script_rosseta.dominio.entities.fluency_catalog import FluencyCatalog
from Resolucion_script_rosseta.dominio.entities.fluency_course import (
    FluencyCourse,
    FluencySequenceRef,
)
from Resolucion_script_rosseta.dominio.entities.fluency_sequence import FluencySequence
from Resolucion_script_rosseta.dominio.entities.fluency_step import FluencyStep
from Resolucion_script_rosseta.dominio.values.fluency_progress_result import (
    FluencyProgressResult,
)


class _FakeApi:
    def __init__(self, pending_seqs, complete_after=True):
        self._pending = pending_seqs
        self._complete_after = complete_after
        self.add_progress_calls = []
        self.add_usage_overhead_calls = []
        self._catalog_reads = 0

    def _catalog(self, complete):
        pct = 1.0 if complete else 0.0
        seqs = [
            FluencySequenceRef(sid, f"Lesson {sid}", percent_complete=pct)
            for sid in self._pending
        ]
        return FluencyCatalog(
            courses=[FluencyCourse("c1", "p", "Course", "B1", "Topic", seqs)]
        )

    async def get_catalog(self, authorization, locale=None):
        self._catalog_reads += 1
        # First read: pending. Second (verify) read: complete if configured.
        complete = self._catalog_reads > 1 and self._complete_after
        return self._catalog(complete)

    async def get_sequence(self, authorization, course_id, sequence_id, locale=None):
        return FluencySequence(
            sequence_id=sequence_id,
            course_id=course_id,
            title="Lesson",
            version=1,
            activities=[
                FluencyActivity(
                    "a1", "mc", "practice", "tree",
                    [FluencyStep("s1", "multipleChoice", ["opt"])],
                )
            ],
        )

    async def add_progress(self, authorization, user_id, messages):
        self.add_progress_calls.append(messages)
        return FluencyProgressResult(
            success=True, status=200, activity_id=messages[0]["activityId"],
            message_count=len(messages),
        )

    async def add_usage_overhead(self, authorization, user_id, messages):
        self.add_usage_overhead_calls.append(messages)
        return FluencyProgressResult(
            success=True, status=200,
            course_id=messages[0]["learningContext"],
            message_count=len(messages),
        )

    async def get_progress(self, authorization, course_id):
        # Minimal authoritative-progress shape for the verify step.
        return [
            {
                "courseId": course_id,
                "percentComplete": 1.0,
                "sequences": [
                    {
                        "sequenceId": sid,
                        "percentComplete": 1.0,
                        "bestGrade": 1,
                        "countOfActivities": 1,
                        "activities": [
                            {
                                "activityId": "a1",
                                "percentComplete": 1.0,
                                "bestGrade": 1,
                                "attempts": [],
                            }
                        ],
                    }
                    for sid in self._pending
                ],
            }
        ]


def _run(orch):
    return asyncio.run(orch.execute({"authorization": "Bearer x", "user_id": "u1"}))


class _ManyLessonsCourseApi(_FakeApi):
    """A course with several already-done lessons plus the pending ones."""

    async def get_catalog(self, authorization, locale=None):
        self._catalog_reads += 1
        complete = self._catalog_reads > 1 and self._complete_after
        done = [
            FluencySequenceRef(f"done-{n}", f"Lesson done-{n}", percent_complete=1.0)
            for n in range(1, 10)
        ]
        pending = [
            FluencySequenceRef(sid, f"Lesson {sid}", percent_complete=1.0 if complete else 0.0)
            for sid in self._pending
        ]
        return FluencyCatalog(
            courses=[FluencyCourse("c1", "p", "Course", "B1", "Topic", done + pending)]
        )


class _RateLimitedApi(_FakeApi):
    """Fails with rate_limited for the first `fail_times` calls, then succeeds."""

    def __init__(self, pending_seqs, fail_times):
        super().__init__(pending_seqs)
        self._fail_times = fail_times
        self.attempts = 0

    async def add_progress(self, authorization, user_id, messages):
        self.attempts += 1
        if self.attempts <= self._fail_times:
            return FluencyProgressResult(
                success=False, status=200, rate_limited=True,
                activity_id=messages[0]["activityId"], message_count=len(messages),
            )
        return await super().add_progress(authorization, user_id, messages)


class _InterruptAfterFirstSuccessApi(_FakeApi):
    """Simulates a cancelled/failed run after its first accepted activity."""

    async def add_progress(self, authorization, user_id, messages):
        if self.add_progress_calls:
            raise RuntimeError("run interrupted")
        return await super().add_progress(authorization, user_id, messages)


class _SpeechApi(_FakeApi):
    def __init__(self, complete_after=True):
        super().__init__(["seq-a"])
        self._speech_complete = complete_after

    async def get_sequence(self, authorization, course_id, sequence_id, locale=None):
        return FluencySequence(
            sequence_id=sequence_id,
            course_id=course_id,
            title="Lesson seq-a",
            version=1,
            activities=[
                FluencyActivity(
                    "voice-a",
                    "DialogueExpressionWithReco",
                    "practice",
                    "tree",
                    [
                        FluencyStep("speech-1", "multipleChoice", ["answer-1"]),
                        FluencyStep("speech-2", "multipleChoice", ["answer-2"]),
                    ],
                )
            ],
        )

    async def get_progress(self, authorization, course_id):
        pct = 1.0 if self._speech_complete else 0.0
        return [
            {
                "courseId": course_id,
                "sequences": [
                    {
                        "sequenceId": "seq-a",
                        "percentComplete": pct,
                        "bestGrade": pct,
                        "countOfActivities": 1,
                        "activities": [
                            {
                                "activityId": "voice-a",
                                "percentComplete": pct,
                                "bestGrade": pct,
                                "attempts": [],
                            }
                        ],
                    }
                ],
            }
        ]


class _SpeechSpy:
    def __init__(self, succeeds=True):
        self.succeeds = succeeds
        self.calls = []

    async def complete_activity(self, **kwargs):
        self.calls.append(kwargs)
        return self.succeeds


class _RaisingUsageOverheadApi(_FakeApi):
    """AddUsageOverhead es telemetría: si revienta, la lección ya está enviada."""

    async def add_usage_overhead(self, authorization, user_id, messages):
        self.add_usage_overhead_calls.append(messages)
        raise RuntimeError("gaia-server rejected the message")


class TestCompleteFluencyOrchestrator:
    def test_usage_overhead_disabled_by_default(self):
        api = _FakeApi(["seq-a"])
        orch = CompleteFluencyOrchestrator(api_port=api, max_lessons=1)
        _run(orch)
        assert api.add_usage_overhead_calls == []

    def test_usage_overhead_sent_when_enabled(self):
        api = _FakeApi(["seq-a"])
        orch = CompleteFluencyOrchestrator(
            api_port=api, max_lessons=1, send_usage_overhead=True
        )
        _run(orch)
        assert len(api.add_usage_overhead_calls) == 1
        assert api.add_usage_overhead_calls[0][0]["learningContext"] == "c1"

    def test_usage_overhead_failure_does_not_block_completion(self):
        api = _RaisingUsageOverheadApi(["seq-a"])
        orch = CompleteFluencyOrchestrator(
            api_port=api, max_lessons=1, send_usage_overhead=True
        )
        _run(orch)
        # The activity itself still landed via add_progress despite the
        # telemetry call raising.
        assert len(api.add_progress_calls) == 1
        assert len(api.add_usage_overhead_calls) == 1

    def test_respects_max_lessons(self):
        api = _FakeApi(["seq-a", "seq-b", "seq-c"])
        orch = CompleteFluencyOrchestrator(api_port=api, max_lessons=1)
        _run(orch)
        # only one lesson -> one activity -> one add_progress call
        assert len(api.add_progress_calls) == 1

    def test_no_limit_completes_all_pending(self):
        api = _FakeApi(["seq-a", "seq-b", "seq-c"])
        orch = CompleteFluencyOrchestrator(api_port=api, max_lessons=None)
        _run(orch)
        assert len(api.add_progress_calls) == 3

    def test_duration_ms_is_budgeted_instead_of_flat_default(self):
        api = _FakeApi(["seq-a"])
        # One lesson, one step -> the whole budget lands on that single step.
        calc = FluencyDurationCalculator(total_course_hours=1.0)
        orch = CompleteFluencyOrchestrator(
            api_port=api, max_lessons=1, duration_calculator=calc
        )
        _run(orch)
        duration_ms = api.add_progress_calls[0][0]["durationMs"]
        expected = calc.total_course_ms
        # Two rounds of +/-33% jitter (per-lesson, then per-step) compound, so
        # allow the wider combined range rather than a single +/-33% band.
        assert expected * 4 // 9 <= duration_ms <= expected * 16 // 9

    def test_duration_budget_divides_by_course_total_lessons_not_run_batch(self):
        # A course with 10 total lessons (9 already done, 1 pending). A run
        # that only processes that 1 pending lesson must still divide the
        # budget by the course's 10 lessons, not by "1 lesson this run" --
        # dividing by the run's own tiny batch inflates each step to tens of
        # minutes of fabricated study time.
        api = _ManyLessonsCourseApi(["seq-a"])
        calc = FluencyDurationCalculator(total_course_hours=1.0)
        orch = CompleteFluencyOrchestrator(
            api_port=api, max_lessons=None, duration_calculator=calc
        )
        _run(orch)
        duration_ms = api.add_progress_calls[0][0]["durationMs"]
        expected = calc.total_course_ms // 10
        assert expected * 4 // 9 <= duration_ms <= expected * 16 // 9

    def test_lesson_filter_targets_named_lesson(self):
        api = _FakeApi(["seq-a", "seq-b", "seq-c"])
        orch = CompleteFluencyOrchestrator(
            api_port=api, max_lessons=None, lesson_filter="seq-b"
        )
        _run(orch)
        # Only the matching lesson's activity is sent.
        assert len(api.add_progress_calls) == 1
        assert api.add_progress_calls[0][0]["sequenceId"] == "seq-b"

    def test_dry_run_sends_nothing(self):
        api = _FakeApi(["seq-a"])
        orch = CompleteFluencyOrchestrator(api_port=api, max_lessons=None, dry_run=True)
        _run(orch)
        assert api.add_progress_calls == []

    def test_state_skips_completed_activity(self, tmp_path):
        api = _FakeApi(["seq-a"])
        # Pre-mark the activity as done in state.
        from Resolucion_script_rosseta.infraestructura.state import RunProgressState

        state = RunProgressState(tmp_path / "fluency_u1.json")
        state.mark_done(fluency_activity_key("c1", "seq-a", "a1"))
        state.save()

        orch = CompleteFluencyOrchestrator(
            api_port=api, state_dir=tmp_path, max_lessons=None
        )
        _run(orch)
        assert api.add_progress_calls == []

    def test_retries_on_rate_limit_then_succeeds(self, tmp_path):
        api = _RateLimitedApi(["seq-a"], fail_times=2)
        orch = CompleteFluencyOrchestrator(
            api_port=api, state_dir=tmp_path, max_lessons=None,
            delay_ms=0, max_retries=5,
        )
        _run(orch)
        # 2 failures + 1 success = 3 attempts, and the activity ends up done.
        assert api.attempts == 3
        from Resolucion_script_rosseta.infraestructura.state import RunProgressState

        reloaded = RunProgressState(tmp_path / "fluency_u1.json")
        assert reloaded.is_done(fluency_activity_key("c1", "seq-a", "a1"))

    def test_gives_up_after_max_retries(self):
        api = _RateLimitedApi(["seq-a"], fail_times=99)
        orch = CompleteFluencyOrchestrator(
            api_port=api, max_lessons=None, delay_ms=0, max_retries=3,
        )
        _run(orch)
        # 1 initial + 3 retries = 4 attempts, then gives up (activity not done).
        assert api.attempts == 4

    def test_activity_steps_sent_in_single_batched_call(self):
        api = _FakeApi(["seq-a"])
        orch = CompleteFluencyOrchestrator(api_port=api, delay_ms=0)
        activity = FluencyActivity(
            "d", "DialogueExpressionWithoutReco", "practice", "tree",
            [FluencyStep(f"s{i}", "multipleChoice", ["x"]) for i in range(3)],
        )
        seq = FluencySequence("seq-a", "c1", "L", 1, [activity])
        messages = orch.builder.build_activity_messages(seq, activity)
        asyncio.run(orch._send_activity("auth", "u1", activity, messages))
        assert len(api.add_progress_calls) == 1
        assert len(api.add_progress_calls[0]) == 3

    def test_persists_state_after_send(self, tmp_path):
        api = _FakeApi(["seq-a"])
        orch = CompleteFluencyOrchestrator(
            api_port=api, state_dir=tmp_path, max_lessons=None
        )
        _run(orch)
        from Resolucion_script_rosseta.infraestructura.state import RunProgressState

        reloaded = RunProgressState(tmp_path / "fluency_u1.json")
        assert reloaded.is_done(fluency_activity_key("c1", "seq-a", "a1"))

    def test_persists_successes_before_a_later_run_interruption(self, tmp_path):
        api = _InterruptAfterFirstSuccessApi(["seq-a", "seq-b"])
        orch = CompleteFluencyOrchestrator(
            api_port=api, state_dir=tmp_path, max_lessons=None
        )

        with pytest.raises(RuntimeError, match="run interrupted"):
            _run(orch)

        from Resolucion_script_rosseta.infraestructura.state import RunProgressState

        reloaded = RunProgressState(tmp_path / "fluency_u1.json")
        assert reloaded.is_done(fluency_activity_key("c1", "seq-a", "a1"))

    def test_speech_activity_uses_browser_and_not_add_progress(self, tmp_path):
        api = _SpeechApi(complete_after=True)
        speech = _SpeechSpy()
        orch = CompleteFluencyOrchestrator(
            api_port=api,
            speech_port=speech,
            state_dir=tmp_path,
            max_lessons=None,
        )

        _run(orch)

        assert api.add_progress_calls == []
        assert speech.calls == [
            {
                "course_title": "Course",
                "lesson_title": "Lesson seq-a",
                "activity_id": "voice-a",
                "expected_steps": 2,
            }
        ]
        from Resolucion_script_rosseta.infraestructura.state import RunProgressState

        state = RunProgressState(tmp_path / "fluency_u1.json")
        assert state.is_done(fluency_activity_key("c1", "seq-a", "voice-a"))

    def test_speech_activity_is_not_saved_without_authoritative_completion(self, tmp_path):
        api = _SpeechApi(complete_after=False)
        speech = _SpeechSpy()
        orch = CompleteFluencyOrchestrator(
            api_port=api,
            speech_port=speech,
            state_dir=tmp_path,
            max_lessons=None,
        )

        _run(orch)

        from Resolucion_script_rosseta.infraestructura.state import RunProgressState

        state = RunProgressState(tmp_path / "fluency_u1.json")
        assert not state.is_done(fluency_activity_key("c1", "seq-a", "voice-a"))

