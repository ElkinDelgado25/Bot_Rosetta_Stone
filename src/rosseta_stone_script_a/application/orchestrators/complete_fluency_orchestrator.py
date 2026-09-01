"""Write phase for Fluency Builder: fabricates completion for pending B1 lessons.

Safety: bounded by ``max_lessons`` (default 1 for a controlled first run) and a
``dry_run`` mode that builds and logs messages without sending them. State is
persisted per activity so re-runs skip what already succeeded. After writing, the
catalog is re-read to verify percentComplete actually moved.
"""

import asyncio
from typing import Any, Dict, Optional

from rosseta_stone_script_a.application.ports.fluency_api import FluencyApiPort
from rosseta_stone_script_a.application.ports.fluency_speech import FluencySpeechPort
from rosseta_stone_script_a.application.ports.orchestrator import OrchestratorPort
from rosseta_stone_script_a.application.services.fluency_duration_calculator import (
    FluencyDurationCalculator,
)
from rosseta_stone_script_a.application.services.fluency_progress_builder import (
    DEFAULT_STEP_DURATION_MS,
    FluencyProgressBuilder,
)
from rosseta_stone_script_a.domain.entities.fluency_catalog import FluencyCatalog
from rosseta_stone_script_a.domain.errors import SessionCaptureIncomplete
from rosseta_stone_script_a.infrastructure.state import RunProgressState
from rosseta_stone_script_a.shared import events


# Tipos que la API no acredita por mucho que se le mande el mensaje correcto:
# el servidor sube ``attempts`` y deja ``percentComplete=0``. Se completan
# abriendo la actividad en el navegador y dejando que el reproductor genere el
# resultado real.
#
# Solo ``DialogueExpressionWithReco``, y es a propósito: es el único con botón
# de micrófono, que es lo que esta ruta sabe manejar.
#
# Se probó a meter aquí ``DialogueExpressionWithoutReco`` y salió mal: "Without
# Reco" significa literalmente sin reconocimiento de voz, así que la actividad
# no tiene micrófono, la espera agotaba 90 s por actividad y terminaba fallando
# igual. Queda como estaba: por API tampoco se completa, así que sigue siendo un
# hueco abierto — pero un hueco barato, no uno que cuesta minuto y medio.
#
# Para probar otro tipo sin tocar código: FLUENCY_BROWSER_EXTRA_TYPES=Tipo1,Tipo2
BROWSER_COMPLETED_TYPES = ("DialogueExpressionWithReco",)


def fluency_activity_key(course_id: str, sequence_id: str, activity_id: str) -> str:
    return f"fluency|{course_id}|{sequence_id}|{activity_id}"


class CompleteFluencyOrchestrator(OrchestratorPort):
    def __init__(
        self,
        api_port: FluencyApiPort,
        state_dir=None,
        max_lessons: Optional[int] = 1,
        dry_run: bool = False,
        course_filter: Optional[str] = None,
        lesson_filter: Optional[str] = None,
        delay_ms: int = 500,
        max_retries: int = 5,
        builder: Optional[FluencyProgressBuilder] = None,
        speech_port: Optional[FluencySpeechPort] = None,
        duration_calculator: Optional[FluencyDurationCalculator] = None,
        send_usage_overhead: bool = False,
        browser_completed_types: Optional[tuple] = None,
    ):
        super().__init__()
        self.api_port = api_port
        self.max_lessons = max_lessons
        self.dry_run = dry_run
        self.course_filter = (course_filter or "").strip().lower() or None
        self.lesson_filter = (lesson_filter or "").strip().lower() or None
        self.delay_ms = max(0, delay_ms)
        self.max_retries = max(0, max_retries)
        self.builder = builder or FluencyProgressBuilder()
        self.speech_port = speech_port
        self.browser_completed_types = tuple(
            browser_completed_types
            if browser_completed_types is not None
            else BROWSER_COMPLETED_TYPES
        )
        self.duration_calculator = duration_calculator or FluencyDurationCalculator()
        # AddUsageOverhead's schema was never captured from real traffic (see
        # FluencyApiPort.add_usage_overhead); off by default so an unverified
        # mutation never runs against a real account without opting in.
        self.send_usage_overhead = send_usage_overhead
        self._state_dir = state_dir
        # Resolved in execute(), once the run knows whose account this is. A
        # single shared file would make user B skip the activities user A
        # completed: the keys are course|sequence|activity, with no account in
        # them, so one user's progress reads as everyone's.
        self._state: RunProgressState | None = None

    async def execute(self, captured_data: Dict[str, Any]) -> None:
        authorization = captured_data.get("authorization") or ""
        user_id = captured_data.get("user_id")
        locale = captured_data.get("lang_code")

        # Without the gaia token every call below is an anonymous 401. Say so
        # here instead of failing later with an HTTP error that hides the cause.
        if not authorization:
            self.logger.error("No hay authorization de gaia. No se envió nada.")
            raise SessionCaptureIncomplete(["authorization"], product="Fluency Builder")

        self._state = self._state_for(user_id, captured_data)

        mode = "DRY-RUN" if self.dry_run else "LIVE"
        self.logger.info(
            f"Fluency write phase ({mode}), max_lessons={self.max_lessons}"
        )

        catalog = await self.api_port.get_catalog(authorization, locale=locale)
        pending = self._pending_lessons(catalog)
        self.logger.info(f"{len(pending)} pending lessons found")

        if self.course_filter or self.lesson_filter:
            pending = self._apply_filters(pending)
            self.logger.info(
                f"{len(pending)} lessons match filters "
                f"(course~{self.course_filter!r}, lesson~{self.lesson_filter!r})"
            )

        if self.max_lessons is not None:
            pending = pending[: self.max_lessons]

        touched = []
        for course, seq_ref in pending:
            sent = await self._complete_lesson(
                authorization, user_id, locale, course, seq_ref
            )
            touched.append((course, seq_ref, sent))

        if self._state:
            self._state.save()

        await self._verify(authorization, touched)

    def _state_for(
        self, user_id: Optional[str], captured_data: Dict[str, Any]
    ) -> Optional[RunProgressState]:
        """One state file per account: ``fluency_<user_id>.json``.

        Falls back to the account email, and only then to a shared file — the
        same order ``StateStore`` uses for Foundations.
        """
        if not self._state_dir:
            return None
        email = (captured_data.get("credentials") or {}).get("email")
        key = user_id or email or "default_account"
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in str(key))
        return RunProgressState(self._state_dir / f"fluency_{safe}.json")

    async def _complete_lesson(
        self, authorization, user_id, locale, course, seq_ref
    ) -> dict:
        """Send progress for a lesson. Returns {activity_id: activityAttemptId} sent."""
        self.logger.info(
            f"Completing lesson {course.title!r} / {seq_ref.title!r} "
            f"(currently {seq_ref.percent_complete:.0%})"
        )
        sequence = await self.api_port.get_sequence(
            authorization,
            course_id=course.course_id,
            sequence_id=seq_ref.sequence_id,
            locale=locale,
        )

        sent_attempts: dict = {}
        ordered_activities = []
        seen_activity_ids: set = set()
        for activity in sequence.activities:
            # getSequence can list the same activityId twice (e.g. a dialogue that
            # opens and closes the lesson); progress is keyed by activityId, so send
            # each once.
            if activity.activity_id in seen_activity_ids:
                continue
            seen_activity_ids.add(activity.activity_id)
            ordered_activities.append(activity)

        total_activities = len(ordered_activities)

        # Speech activities are timed by the browser itself; only budget the
        # activities this method fabricates messages for.
        fabricated_step_count = sum(
            1
            for a in ordered_activities
            if a.activity_type not in self.browser_completed_types
            for s in a.steps
            if s.step_id
        )
        # Divide by how many lessons the COURSE has (assigned, not just
        # pending) — a run's own batch is often just 1-5 lessons (see
        # FLUENCY_MAX_LESSONS), and budgeting against that instead of the
        # course's real size would inflate each step to tens of minutes.
        lesson_budget_ms = self.duration_calculator.lesson_budget_ms(
            len(course.sequences)
        )
        step_durations = iter(
            self.duration_calculator.step_durations_ms(
                lesson_budget_ms, fabricated_step_count
            )
        )

        def _next_duration_ms() -> int:
            return next(step_durations, DEFAULT_STEP_DURATION_MS)

        for activity_number, activity in enumerate(ordered_activities, start=1):
            activity_label = (
                f"{course.title} / {seq_ref.title} / {activity.activity_type}"
            )
            self.logger.info(
                f"  Completing activity {activity_number}/{total_activities}: "
                f"{activity_label} (id={activity.activity_id})"
            )

            key = fluency_activity_key(
                course.course_id, sequence.sequence_id, activity.activity_id
            )
            is_speech = activity.activity_type in self.browser_completed_types
            if not is_speech and self._state and self._state.is_done(key):
                self.logger.info(
                    f"  Skipping activity {activity_number}/{total_activities}: "
                    f"{activity_label} (already done)"
                )
                continue

            if is_speech:
                success = await self._complete_speech_activity(
                    authorization=authorization,
                    course=course,
                    seq_ref=seq_ref,
                    activity=activity,
                )
                if success:
                    self._mark_done(key)
                events.emit(
                    "path_done",
                    ok=success,
                    course=course.title,
                    unit=None,
                    lesson=seq_ref.title,
                    path_type=activity.activity_type,
                    done_total=self._state.total_done() if self._state else None,
                )
                continue

            messages = self.builder.build_activity_messages(
                sequence, activity, next_duration_ms=_next_duration_ms
            )
            if not messages:
                self.logger.warning(
                    f"  Skipping activity {activity_number}/{total_activities}: "
                    f"{activity_label} (no steps to send)"
                )
                continue

            if self.dry_run:
                self.logger.info(
                    f"  [DRY-RUN] Would update activity "
                    f"{activity_number}/{total_activities}: {activity_label} "
                    f"({len(messages)} steps)"
                )
                continue

            success = await self._send_activity(
                authorization, user_id, activity, messages
            )
            if success:
                self.logger.info(
                    f"  Successfully updated activity "
                    f"{activity_number}/{total_activities}: {activity_label} "
                    f"({len(messages)} steps)"
                )
                sent_attempts[activity.activity_id] = messages[0]["activityAttemptId"]
                self._mark_done(key)
                if self.send_usage_overhead:
                    await self._send_usage_overhead(
                        authorization, user_id, sequence, activity, messages
                    )
            else:
                self.logger.error(
                    f"  FAILED activity {activity_number}/{total_activities}: "
                    f"{activity_label}"
                )

            # Structured twin of the log line above, so the web UI can show
            # progress per lesson for Fluency too, not just Foundations.
            events.emit(
                "path_done",
                ok=success,
                course=course.title,
                # Fluency has no unit index; the lesson title is the useful part.
                unit=None,
                lesson=seq_ref.title,
                path_type=activity.activity_type,
                done_total=self._state.total_done() if self._state else None,
            )

            if self.delay_ms:
                await asyncio.sleep(self.delay_ms / 1000)

        return sent_attempts

    def _mark_done(self, key: str) -> None:
        """Persist each accepted activity immediately.

        A web run can be cancelled while it is processing a long course. Saving
        only at the end would lose every successful activity from that partial
        run and make the next run send them again.
        """
        if self._state:
            self._state.mark_done(key)
            self._state.save()

    async def _complete_speech_activity(
        self, *, authorization, course, seq_ref, activity
    ) -> bool:
        if self.dry_run:
            self.logger.info("  [DRY-RUN] Would complete conversation in browser")
            return False
        if not self.speech_port:
            self.logger.warning(
                "  Skipping conversation: browser speech automation is disabled"
            )
            return False

        self.logger.info(
            "  Completing conversation through browser speech recognition "
            "(%d steps)",
            len(activity.steps),
        )
        browser_ok = await self.speech_port.complete_activity(
            course_title=course.title,
            lesson_title=seq_ref.title,
            activity_id=activity.activity_id,
            expected_steps=len(activity.steps),
        )
        if not browser_ok:
            return False

        progress = await self.api_port.get_progress(authorization, course.course_id)
        seq = self._find_sequence(progress, seq_ref.sequence_id)
        if not seq:
            self.logger.error("  Speech verification could not find the lesson")
            return False
        for item in seq.get("activities") or []:
            if item.get("activityId") == activity.activity_id:
                complete = (item.get("percentComplete") or 0.0) >= 1.0
                self.logger.info(
                    "  Speech verification: percentComplete=%s bestGrade=%s",
                    item.get("percentComplete"),
                    item.get("bestGrade"),
                )
                return complete
        self.logger.error("  Speech verification could not find the activity")
        return False

    async def _send_activity(self, authorization, user_id, activity, messages) -> bool:
        """Send an activity's step messages in a single batched call.

        Speech activities are routed through ``speech_port`` before reaching this
        method because Gaia ignores fabricated recognition scores.
        """
        result = await self._send_with_retry(authorization, user_id, messages)
        if not result.success and not result.rate_limited:
            self.logger.error(
                f"    status={result.status} "
                f"{result.error or result.response_body[:200]}"
            )
        return result.success

    async def _send_usage_overhead(
        self, authorization, user_id, sequence, activity, messages
    ) -> None:
        """Best-effort AddUsageOverhead call for a just-completed activity.

        Unverified/inferred mutation (FluencyApiPort.add_usage_overhead) — a
        failure here (including a GraphQL schema error) is expected until it is
        validated against real traffic, and must never affect the activity's
        already-successful AddProgress result.
        """
        total_duration_ms = sum(m.get("durationMs", 0) for m in messages)
        overhead_message = self.builder.build_usage_overhead_message(
            sequence, activity, total_duration_ms
        )
        try:
            result = await self.api_port.add_usage_overhead(
                authorization, user_id, [overhead_message]
            )
            if not result.success:
                self.logger.debug(
                    "  AddUsageOverhead not accepted (unverified mutation): "
                    f"status={result.status} {result.error or result.response_body[:200]}"
                )
        except Exception as exc:
            self.logger.debug(f"  AddUsageOverhead call raised (ignored): {exc}")

    async def _send_with_retry(self, authorization, user_id, messages):
        """Send one activity, retrying with exponential backoff on rate limiting."""
        result = await self.api_port.add_progress(authorization, user_id, messages)
        attempt = 0
        while result.rate_limited and attempt < self.max_retries:
            backoff = min(2 ** attempt, 30)
            self.logger.warning(
                f"  rate limited; backing off {backoff}s "
                f"(retry {attempt + 1}/{self.max_retries})"
            )
            await asyncio.sleep(backoff)
            result = await self.api_port.add_progress(authorization, user_id, messages)
            attempt += 1
        return result

    async def _verify(self, authorization, touched) -> None:
        if self.dry_run or not touched:
            return
        self.logger.info("Verifying via authoritative getProgress...")
        for course, seq_ref, sent in touched:
            progress = await self.api_port.get_progress(authorization, course.course_id)
            seq = self._find_sequence(progress, seq_ref.sequence_id)
            if not seq:
                self.logger.warning(
                    f"  {seq_ref.title}: sequence not found in getProgress"
                )
                continue

            pct = seq.get("percentComplete", 0.0)
            verdict = "COMPLETE" if pct >= 1.0 else "partial"
            self.logger.info(
                f"  {course.title} / {seq_ref.title}: "
                f"{seq_ref.percent_complete:.0%} -> {pct:.0%} ({verdict}), "
                f"bestGrade={seq.get('bestGrade')}"
            )
            self._diagnose_activities(seq, sent)

    def _find_sequence(self, progress, sequence_id):
        for course in progress or []:
            for seq in course.get("sequences") or []:
                if seq.get("sequenceId") == sequence_id:
                    return seq
        return None

    def _diagnose_activities(self, seq, sent) -> None:
        """Log which activities are still pending and whether our attempts landed."""
        pending = [
            a for a in (seq.get("activities") or [])
            if (a.get("percentComplete") or 0.0) < 1.0
        ]
        self.logger.info(
            f"    {len(pending)}/{seq.get('countOfActivities')} activities still < 100%"
        )
        for a in pending[:10]:
            aid = a.get("activityId")
            attempt_ids = {
                att.get("activityAttemptId") for att in (a.get("attempts") or [])
            }
            landed = sent.get(aid) in attempt_ids if aid in sent else False
            self.logger.info(
                f"    pending activity {aid}: pct={a.get('percentComplete')} "
                f"bestGrade={a.get('bestGrade')} "
                f"our_attempt_registered={landed} attempts={len(attempt_ids)}"
            )

    def _pending_lessons(self, catalog: FluencyCatalog):
        pending = []
        for course in catalog.courses:
            for seq in course.sequences:
                if seq.percent_complete < 1.0:
                    pending.append((course, seq))
        # Least-complete first: validation lands on a genuinely incomplete lesson
        # (a 0% one) so a real 0 -> 100% transition is observable, and completion
        # tackles the most-pending work first.
        pending.sort(key=lambda cs: cs[1].percent_complete)
        return pending

    def _apply_filters(self, pending):
        def matches(course, seq):
            if self.course_filter and self.course_filter not in (course.title or "").lower():
                return False
            if self.lesson_filter and self.lesson_filter not in (seq.title or "").lower():
                return False
            return True

        return [(c, s) for (c, s) in pending if matches(c, s)]
