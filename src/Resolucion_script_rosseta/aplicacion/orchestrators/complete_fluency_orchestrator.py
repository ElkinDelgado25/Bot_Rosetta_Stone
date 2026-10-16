"""Write phase for Fluency Builder: fabricates completion for pending B1 lessons.

Safety: bounded by ``max_lessons`` (default 1 for a controlled first run) and a
``dry_run`` mode that builds and logs messages without sending them. State is
persisted per activity so re-runs skip what already succeeded. After writing, the
catalog is re-read to verify percentComplete actually moved.
"""

import asyncio
from typing import Any, Dict, Optional

from Resolucion_script_rosseta.aplicacion.ports.fluency_api import FluencyApiPort
from Resolucion_script_rosseta.aplicacion.ports.fluency_speech import FluencySpeechPort
from Resolucion_script_rosseta.aplicacion.ports.orchestrator import OrchestratorPort
from Resolucion_script_rosseta.aplicacion.services.fluency_duration_calculator import (
    FluencyDurationCalculator,
)
from Resolucion_script_rosseta.aplicacion.services.fluency_progress_builder import (
    DEFAULT_STEP_DURATION_MS,
    FluencyProgressBuilder,
)
from Resolucion_script_rosseta.dominio.entities.fluency_catalog import FluencyCatalog
from Resolucion_script_rosseta.dominio.errors import BrowserGone, SessionCaptureIncomplete
from Resolucion_script_rosseta.infraestructura.state import RunProgressState
from Resolucion_script_rosseta.compartido import events


# Tipos que la API no acredita por mucho que se le mande el mensaje correcto:
# el servidor sube ``attempts`` y deja ``percentComplete=0``. Se completan
# abriendo la actividad en el navegador y dejando que el reproductor genere el
# resultado real.
#
# Son exactamente las dos conversaciones, y no es casualidad: cruzando el
# catálogo entero, ``ordering: "tree"`` aparece en 46 actividades — las 27
# ``WithReco`` más las 19 ``WithoutReco`` — y en ninguna otra. Todo lo demás es
# ``fixed`` o ``random`` y la API lo acredita sin rechistar. Lo que el servidor
# no acepta fabricado es el árbol, no la voz.
#
# ``WithoutReco`` estuvo fuera de esta lista por una conclusión mal sacada: se
# enrutó aquí, la ruta esperaba un micrófono que esa actividad no tiene, agotaba
# 90 s y fallaba — y se anotó como "no se puede". Lo que no se podía era
# *esperar el micrófono*: sus pasos son ``inputType: select``, se contestan
# pulsando. La página distingue ahora los dos modos (``_input_mode``).
#
# Para probar otro tipo sin tocar código: FLUENCY_BROWSER_EXTRA_TYPES=Tipo1,Tipo2
BROWSER_COMPLETED_TYPES = (
    "DialogueExpressionWithReco",
    "DialogueExpressionWithoutReco",
)


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
        progress_by_course: Dict[str, Any] = {}
        for course in catalog.courses:
            progress_by_course[course.course_id] = await self.api_port.get_progress(
                authorization, course.course_id
            )
        pending = self._pending_lessons(catalog, progress_by_course)
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
            try:
                sent = await self._complete_lesson(
                    authorization,
                    user_id,
                    locale,
                    course,
                    seq_ref,
                    progress=progress_by_course.get(course.course_id),
                )
            except BrowserGone as exc:
                # Se para aquí a propósito. Sin esto, la corrida del 02-09 a
                # las 10:29 siguió pidiendo lecciones con el navegador ya
                # muerto y acabó en un traceback que no nombraba la causa.
                #
                # Lo enviado se guarda antes de volver a lanzar, pero **se
                # vuelve a lanzar**: una corrida que se quedó a medias no es un
                # éxito, y salir con 0 es justo el silencio que este proyecto
                # decidió no tener ("sesión incompleta = error, no silencio").
                # Verificar tampoco tiene sentido: hace falta el navegador.
                self.logger.error("%s", exc)
                self.logger.info(
                    "  Se envió lo de %d lecciones antes de perderlo; el resto "
                    "queda pendiente para la próxima corrida.",
                    len(touched),
                )
                if self._state:
                    self._state.save()
                raise
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
        self, authorization, user_id, locale, course, seq_ref, progress=None
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
        seq_progress = self._find_sequence(progress, seq_ref.sequence_id)

        # Speech activities are timed by the browser itself; only budget the
        # activities this method fabricates messages for.
        fabricated_step_count = sum(
            (
                len(s.correct_answer_ids)
                if (s.type or "").lower() == "card" and s.correct_answer_ids
                else 1
            )
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
                if self._activity_complete_on_server(
                    seq_progress, activity.activity_id
                ):
                    self.logger.info(
                        f"  Skipping activity {activity_number}/{total_activities}: "
                        f"{activity_label} (already done)"
                    )
                    continue
                self.logger.info(
                    "  Skipping local state for %s: el servidor aún la tiene "
                    "al %.0f%%; se vuelve a enviar",
                    activity_label,
                    self._activity_percent(seq_progress, activity.activity_id) * 100,
                )

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

        await self._close_map_count_gap(
            authorization, course, seq_ref, ordered_activities
        )
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

    @staticmethod
    def _speech_steps(activity) -> list:
        """Serializa los pasos del árbol para el flujo del navegador.

        Solo viaja lo que la página necesita para elegir tarjeta: el id de cada
        opción, su texto visible, el sha de su audio y los ids aceptados del
        paso.
        """
        return [
            {
                "id": step.step_id,
                "success_ids": list(step.success_answer_ids),
                "options": [
                    {"id": answer.id, "text": answer.text, "sha": answer.audio_sha}
                    for answer in step.answers
                ],
            }
            for step in activity.steps
        ]

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

        # ``len(activity.steps)`` es el árbol entero, no la conversación: una
        # que declaraba 13 nodos tenía 10 enunciados. Va como cota superior y la
        # página corta cuando el reproductor deja de pedir turnos.
        self.logger.info(
            "  Completing conversation in the browser (hasta %d pasos)",
            len(activity.steps),
        )
        browser_ok = await self.speech_port.complete_activity(
            course_title=course.title,
            lesson_title=seq_ref.title,
            activity_id=activity.activity_id,
            expected_steps=len(activity.steps),
            steps=self._speech_steps(activity),
        )
        if not browser_ok:
            return False

        progress = await self.api_port.get_progress(authorization, course.course_id)
        seq = self._find_sequence(progress, seq_ref.sequence_id)
        if not seq:
            self.logger.error("  Speech verification could not find the lesson")
            return False
        found = None
        for item in seq.get("activities") or []:
            if item.get("activityId") == activity.activity_id:
                found = item
                break
        if found is None:
            self.logger.error("  Speech verification could not find the activity")
            return False
        complete = (found.get("percentComplete") or 0.0) >= 1.0
        self.logger.info(
            "  Speech verification: percentComplete=%s bestGrade=%s",
            found.get("percentComplete"),
            found.get("bestGrade"),
        )
        if not complete:
            return False
        # El id único ya está a 100%. Si el mapa cuenta una copia más, eso
        # se cierra después con `_close_map_count_gap`, no invalidando esta.
        return True

    async def _close_map_count_gap(
        self, authorization, course, seq_ref, ordered_activities
    ) -> None:
        """Cierra el hueco de conteo de una lección, si es que se puede.

        Cuando el hueco es exactamente la copia con id duplicado del contenido
        v2 (``count == listadas + 1`` y todo lo listado acreditado), no hay
        nada que jugar: el servidor no acredita la ranura extra y el replay
        del mapa, probado en vivo, la deja igual. La lección se da por
        completa. Para cualquier otro hueco se conserva el replay del árbol,
        que es lo único que puede acreditar una actividad realmente omitida.
        """
        if self.dry_run or not self.speech_port:
            return
        progress = await self.api_port.get_progress(authorization, course.course_id)
        seq = self._find_sequence(progress, seq_ref.sequence_id)
        if not self._omitted_map_slot(seq):
            return
        if self._content_duplicate_gap(seq):
            self.logger.info(
                "  El hueco de conteo es la copia con id duplicado del "
                "diálogo de cierre (bug de contenido v2); la plataforma no "
                "puede acreditarla y lo listado ya está completo: la lección "
                "se cuenta como completa"
            )
            return
        tree = []
        seen: set[str] = set()
        for activity in ordered_activities:
            if (
                activity.activity_type in self.browser_completed_types
                and activity.activity_id
                and activity.activity_id not in seen
            ):
                seen.add(activity.activity_id)
                tree.append(activity)
        if not tree:
            return
        listed = seq.get("activities") or []
        credited = sum(
            1 for a in listed if (a.get("percentComplete") or 0.0) >= 1.0
        )
        self.logger.info(
            "  Queda una copia del diálogo en el mapa "
            "(listed=%s credited=%s count=%s); se juega la que falta",
            len(listed),
            credited,
            seq.get("countOfActivities") or 0,
        )
        for activity in tree:
            await self.speech_port.complete_activity(
                course_title=course.title,
                lesson_title=seq_ref.title,
                activity_id=activity.activity_id,
                expected_steps=len(activity.steps),
                steps=self._speech_steps(activity),
            )
        progress = await self.api_port.get_progress(authorization, course.course_id)
        seq = self._find_sequence(progress, seq_ref.sequence_id)
        if self._content_duplicate_gap(seq):
            self.logger.info(
                "  Tras el replay queda la copia con id duplicado del bug de "
                "contenido v2: no se puede acreditar y la lección se cuenta "
                "como completa"
            )
        elif self._omitted_map_slot(seq):
            listed = seq.get("activities") or []
            credited = sum(
                1 for a in listed if (a.get("percentComplete") or 0.0) >= 1.0
            )
            self.logger.error(
                "  Speech verification: the lesson still has a count gap "
                "(listed=%s credited=%s count=%s)",
                len(listed),
                credited,
                seq.get("countOfActivities") or 0,
            )

    @staticmethod
    def _omitted_map_slot(seq) -> bool:
        """El mapa cuenta una copia que getProgress no lista."""
        if not seq:
            return False
        count = seq.get("countOfActivities") or 0
        listed = seq.get("activities") or []
        return count > len(listed)

    @staticmethod
    def _count_gap(seq) -> bool:
        if not seq:
            return False
        count = seq.get("countOfActivities") or 0
        listed = seq.get("activities") or []
        credited = sum(
            1 for a in listed if (a.get("percentComplete") or 0.0) >= 1.0
        )
        return count > credited or count > len(listed)

    @staticmethod
    def _content_duplicate_gap(seq) -> bool:
        """El ítem que falta es la copia con id duplicado del contenido v2.

        Las lecciones migradas a v2 repiten el ``activityId`` del diálogo de
        cierre: apertura y cierre comparten id. ``countOfActivities`` cuenta
        las dos ranuras del mapa, pero el servidor acredita **ids únicos**,
        así que con todo lo listado al 100% la lección se queda en 16/17
        (94%) para siempre. Verificado contra la definición real
        (``DistilledCourses``), con un replay del propio reproductor y con un
        AddProgress fabricado para el id v1 de cierre: la copia extra nunca
        acredita, ni jugándola a mano en el navegador. La forma exacta del
        hueco (count == listadas + 1 y todas listadas acreditadas) es la que
        delata al duplicado; un hueco con ítems sin acreditar conserva el
        camino de replay normal.
        """
        if not seq:
            return False
        count = seq.get("countOfActivities") or 0
        listed = seq.get("activities") or []
        if count != len(listed) + 1:
            return False
        return all((a.get("percentComplete") or 0.0) >= 1.0 for a in listed)

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
            duplicate_gap = self._content_duplicate_gap(seq)
            verdict = "COMPLETE" if (pct >= 1.0 or duplicate_gap) else "partial"
            note = (
                "; el ítem extra es la copia con id duplicado del bug de "
                "contenido v2 y no puede acreditarse"
                if duplicate_gap and pct < 1.0
                else ""
            )
            self.logger.info(
                f"  {course.title} / {seq_ref.title}: "
                f"{seq_ref.percent_complete:.0%} -> {pct:.0%} ({verdict}), "
                f"bestGrade={seq.get('bestGrade')}{note}"
            )
            self._diagnose_activities(seq, sent, course.title, seq_ref.title)

    def _find_sequence(self, progress, sequence_id):
        for course in progress or []:
            for seq in course.get("sequences") or []:
                if seq.get("sequenceId") == sequence_id:
                    return seq
        return None

    @staticmethod
    def _activity_on_server(seq, activity_id):
        for item in (seq or {}).get("activities") or []:
            if item.get("activityId") == activity_id:
                return item
        return None

    @staticmethod
    def _activity_percent(seq, activity_id) -> float:
        found = CompleteFluencyOrchestrator._activity_on_server(seq, activity_id)
        if found is None:
            return 0.0
        return float(found.get("percentComplete") or 0.0)

    @staticmethod
    def _activity_complete_on_server(seq, activity_id) -> bool:
        return CompleteFluencyOrchestrator._activity_percent(seq, activity_id) >= 1.0

    def _diagnose_activities(self, seq, sent, course_title=None, lesson_title=None) -> None:
        """Log which activities are still pending and whether our attempts landed."""
        listed = seq.get("activities") or []
        pending = [
            a for a in listed
            if (a.get("percentComplete") or 0.0) < 1.0
        ]
        count = seq.get("countOfActivities") or 0
        omitted = max(0, count - len(listed))
        self.logger.info(
            f"    {len(pending)}/{count or len(listed)} activities still < 100%"
            + (f", {omitted} omitted from getProgress" if omitted else "")
        )
        if omitted:
            duplicate_gap = self._content_duplicate_gap(seq)
            if duplicate_gap:
                self.logger.info(
                    "    la ranura extra es la copia con id duplicado del "
                    "diálogo de cierre (bug de contenido v2): no puede "
                    "acreditarse y la lección se cuenta como completa"
                )
            events.emit(
                "path_done",
                ok=duplicate_gap,
                course=course_title,
                unit=None,
                lesson=lesson_title,
                path_type="omitted_duplicate" if duplicate_gap else "omitted",
                done_total=self._state.total_done() if self._state else None,
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

    def _pending_lessons(self, catalog: FluencyCatalog, progress_by_course=None):
        progress_by_course = progress_by_course or {}
        pending = []
        for course in catalog.courses:
            by_id = self._progress_by_sequence(progress_by_course.get(course.course_id))
            for seq in course.sequences:
                if self._lesson_incomplete(seq, by_id.get(seq.sequence_id)):
                    pending.append((course, seq))
        # Least-complete first: validation lands on a genuinely incomplete lesson
        # (a 0% one) so a real 0 -> 100% transition is observable, and completion
        # tackles the most-pending work first.
        pending.sort(key=lambda cs: cs[1].percent_complete)
        return pending

    @staticmethod
    def _progress_by_sequence(progress) -> dict:
        index = {}
        for course in progress or []:
            for seq in course.get("sequences") or []:
                sid = seq.get("sequenceId") or seq.get("id")
                if sid:
                    index[sid] = seq
        return index

    @staticmethod
    def _lesson_incomplete(seq_ref, progress_seq) -> bool:
        if CompleteFluencyOrchestrator._content_duplicate_gap(progress_seq):
            return False
        if seq_ref.percent_complete < 1.0:
            return True
        if not progress_seq:
            return False
        if CompleteFluencyOrchestrator._count_gap(progress_seq):
            return True
        return any((a.get("percentComplete") or 0.0) < 1.0 for a in (progress_seq.get("activities") or []))

    def _apply_filters(self, pending):
        def matches(course, seq):
            if self.course_filter and self.course_filter not in (course.title or "").lower():
                return False
            if self.lesson_filter and self.lesson_filter not in (seq.title or "").lower():
                return False
            return True

        return [(c, s) for (c, s) in pending if matches(c, s)]

