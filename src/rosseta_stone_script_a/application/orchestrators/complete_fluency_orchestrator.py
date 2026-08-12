"""Write phase for Fluency Builder: fabricates completion for pending B1 lessons.

Safety: bounded by ``max_lessons`` (default 1 for a controlled first run) and a
``dry_run`` mode that builds and logs messages without sending them. State is
persisted per activity so re-runs skip what already succeeded. After writing, the
catalog is re-read to verify percentComplete actually moved.
"""

import asyncio
from typing import Any, Dict, Optional

from rosseta_stone_script_a.application.ports.fluency_api import FluencyApiPort
from rosseta_stone_script_a.application.ports.orchestrator import OrchestratorPort
from rosseta_stone_script_a.application.services.fluency_progress_builder import (
    FluencyProgressBuilder,
)
from rosseta_stone_script_a.domain.entities.fluency_catalog import FluencyCatalog
from rosseta_stone_script_a.domain.errors import SessionCaptureIncomplete
from rosseta_stone_script_a.infrastructure.state import RunProgressState
from rosseta_stone_script_a.shared import events


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
        seen_activity_ids: set = set()
        for activity in sequence.activities:
            # getSequence can list the same activityId twice (e.g. a dialogue that
            # opens and closes the lesson); progress is keyed by activityId, so send
            # each once.
            if activity.activity_id in seen_activity_ids:
                continue
            seen_activity_ids.add(activity.activity_id)

            key = fluency_activity_key(
                course.course_id, sequence.sequence_id, activity.activity_id
            )
            if self._state and self._state.is_done(key):
                self.logger.info(f"  activity {activity.activity_id} already done; skip")
                continue

            messages = self.builder.build_activity_messages(sequence, activity)
            if not messages:
                continue

            if self.dry_run:
                self.logger.info(
                    f"  [DRY-RUN] {activity.activity_type} "
                    f"activity={activity.activity_id} -> {len(messages)} messages"
                )
                continue

            success = await self._send_activity(
                authorization, user_id, activity, messages
            )
            if success:
                self.logger.info(
                    f"  sent {activity.activity_type} ({len(messages)} steps)"
                )
                sent_attempts[activity.activity_id] = messages[0]["activityAttemptId"]
                if self._state:
                    self._state.mark_done(key)
            else:
                self.logger.error(f"  FAILED {activity.activity_type}")

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

    async def _send_activity(self, authorization, user_id, activity, messages) -> bool:
        """Send an activity's step messages in a single batched call.

        Note: speech "Conversation Practice" activities (DialogueExpressionWithReco)
        cannot be completed this way — the server records the attempt but keeps the
        activity at percentComplete 0 because it requires a real speech-recognition
        score. Confirmed against a manual capture (identical message, per-step
        submission, and integer score all leave it at 0); not solvable via the API.
        Lessons with one cap in the low-to-mid 90s%. See docs/FLUENCY_BUILDER.md.
        """
        result = await self._send_with_retry(authorization, user_id, messages)
        if not result.success and not result.rate_limited:
            self.logger.error(
                f"    status={result.status} "
                f"{result.error or result.response_body[:200]}"
            )
        return result.success

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
