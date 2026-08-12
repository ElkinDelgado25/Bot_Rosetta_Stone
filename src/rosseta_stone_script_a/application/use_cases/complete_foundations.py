import asyncio
import random
import time
from datetime import date
from pathlib import Path

from rosseta_stone_script_a.application.ports.foundations_api import FoundationsApiPort
from rosseta_stone_script_a.application.ports.use_case import UseCasePort
from rosseta_stone_script_a.application.services.content_filter import ContentFilter
from rosseta_stone_script_a.application.services.path_calculator import PathCalculator
from rosseta_stone_script_a.domain.entities.completion_stats import CompletionStats
from rosseta_stone_script_a.domain.entities.path import Path as RosettaPath
from rosseta_stone_script_a.domain.values.path_score_result import PathScoreResult
from rosseta_stone_script_a.infrastructure.state import (
    RunProgressState,
    StateStore,
    make_path_key,
)
from rosseta_stone_script_a.shared import events


class CompleteFoundationsUseCase(UseCasePort):
    """
    Use case for automatically completing Rosetta Stone Foundations lessons.

    Runs a small randomised batch per invocation and persists progress to a
    JSON state file so that successive scheduler runs resume where they left
    off, spreading a full course over days/weeks.
    """

    def __init__(
        self,
        api_port: FoundationsApiPort,
        units_to_complete: list[int] = None,
        lessons_to_complete: list[int] = None,
        path_types_to_complete: list[str] = None,
        target_score_percent: int = 100,
        max_start_time_offset_ms: int = 300000,
        inter_path_delay_ms: int = 500,
        inter_path_delay_min_ms: int = 1500,
        inter_path_delay_max_ms: int = 5000,
        force_recomplete: bool = False,
        human_mode: bool = False,
        batch_min_paths: int = 6,
        batch_max_paths: int = 14,
        max_paths_per_day: int = 18,
        state_dir: Path | None = None,
    ):
        self.api_port = api_port
        self.stats = CompletionStats()

        self.content_filter = ContentFilter(
            units_to_complete=units_to_complete,
            lessons_to_complete=lessons_to_complete,
            path_types_to_complete=path_types_to_complete,
            force_recomplete=force_recomplete,
        )
        self.path_calculator = PathCalculator(
            target_score_percent=target_score_percent,
            max_start_time_offset_ms=max_start_time_offset_ms,
        )

        # Inter-path delay: prefer explicit min/max; fall back to old single value
        # so existing .env files without the new keys still work.
        self.inter_path_delay_min_ms = inter_path_delay_min_ms
        self.inter_path_delay_max_ms = max(inter_path_delay_max_ms, inter_path_delay_min_ms)
        # Legacy single value — only used if min==max==500 (the old default)
        self.inter_path_delay_ms = inter_path_delay_ms

        # Fast by default: complete every eligible path in one run, no delays.
        # Human mode applies the batch/daily caps and inter-path pauses below.
        self.human_mode = human_mode
        self.batch_min_paths = batch_min_paths
        self.batch_max_paths = max(batch_max_paths, batch_min_paths)
        self.max_paths_per_day = max_paths_per_day

        self._state_store = StateStore(state_dir or Path("state"))

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def execute(
        self,
        authorization: str,
        language_code: str,
        session_token: str,
        school_id: str,
        user_id: str,
        email: str | None = None,
    ) -> CompletionStats:
        """
        Execute one scheduled batch of path completions.

        Args:
            authorization: GraphQL authorization token (JWT)
            language_code: Language code (e.g., ENG)
            session_token: REST API session token
            school_id: School ID
            user_id: User ID
            email: Optional email used as fallback key for state file naming

        Returns:
            CompletionStats: Statistics about what was completed this run
        """
        self.stats = CompletionStats()

        # Load per-account state
        state: RunProgressState = self._state_store.load(user_id, email)
        state.touch_last_run()

        # --- Pick how many paths to submit this run ---
        if self.human_mode:
            # Daily cap check (human mode only).
            done_today = state.count_done_today()
            if done_today >= self.max_paths_per_day:
                self.logger.info(
                    f"Daily cap reached ({done_today}/{self.max_paths_per_day} paths already "
                    f"completed today). Exiting without doing anything."
                )
                state.save()
                return self.stats

            remaining_today = self.max_paths_per_day - done_today
            raw_budget = random.randint(self.batch_min_paths, self.batch_max_paths)
            run_budget = min(raw_budget, remaining_today)
            self.logger.info(
                f"Run budget: {run_budget} paths "
                f"(batch={raw_budget}, daily_remaining={remaining_today})"
            )
        else:
            # Fast mode: no batch/daily cap — submit every eligible path.
            run_budget = None
            self.logger.info("Fast mode: completing all eligible paths this run.")

        self.logger.info("Starting Foundations completion process...")
        if self.content_filter.units_to_complete:
            self.logger.info(f"Target units: {self.content_filter.units_to_complete}")
        else:
            self.logger.info("No specific units configured — processing ALL units.")
        if self.content_filter.lessons_to_complete:
            self.logger.info(f"Target lessons: {self.content_filter.lessons_to_complete}")
        else:
            self.logger.info("No specific lessons configured — processing ALL lessons.")
        if self.content_filter.path_types_to_complete:
            self.logger.info(f"Target path types: {self.content_filter.path_types_to_complete}")
        else:
            self.logger.info("No specific path types configured — processing ALL types.")

        # 1. Fetch Course Menu
        try:
            course_menu = await self.api_port.get_course_menu(authorization, language_code)
        except Exception as e:
            self.logger.error(f"Failed to get course menu: {e}")
            return self.stats

        self.logger.info(f"Fetched course menu. Total units: {len(course_menu.units)}")

        # Count total eligible paths for the summary line
        total_eligible = self._count_eligible_paths(course_menu, state)

        # 2. Collect the batch of paths to submit this run
        batch = self._collect_batch(course_menu, state, run_budget)
        self._record_batch_stats(batch)

        self.logger.info(
            f"Batch collected: {len(batch)} paths to submit this run "
            f"(already done in state: {state.total_done()}, "
            f"total eligible in course: {total_eligible})"
        )

        if not batch:
            remaining_in_course = max(0, total_eligible - state.total_done())
            self.logger.info(
                f"This run: completed 0 paths, {state.total_done()} already done, "
                f"{remaining_in_course} remaining in course; "
                "course may be fully complete or all remaining paths filtered."
            )
            self.stats.units_completed = sorted(
                self._derive_completed_units(course_menu, state)
            )
            state.save()
            return self.stats

        # 3. Pre-compute each path's duration/score, then anchor the batch so its
        #    completions END at ~now and march BACKWARD. This keeps every
        #    `updated_at` <= now (never in the future) while preserving realistic
        #    spacing between paths equal to their `delta_time` durations.
        prepared = [
            (path, self.path_calculator.calculate_path_completion(path, 0, 0))
            for path in batch
        ]
        now_ms = int(time.time() * 1000)
        total_span_ms = sum(calc.time_in_milliseconds for _, calc in prepared)
        end_jitter_ms = random.randint(
            0, self.path_calculator.max_start_time_offset_ms
        )
        # Cursor starts far enough back that, after adding every duration, the
        # final path lands at roughly (now - end_jitter).
        cursor_ms = now_ms - end_jitter_ms - total_span_ms

        # 4. Submit paths sequentially with paced, jittered delays
        paths_this_run = 0
        for idx, (path, calc) in enumerate(prepared):
            cursor_ms += calc.time_in_milliseconds
            result = await self._complete_path(
                path=path,
                session_token=session_token,
                school_id=school_id,
                user_id=user_id,
                duration_ms=calc.time_in_milliseconds,
                questions_correct=calc.questions_correct,
                questions_incorrect=calc.questions_incorrect,
                timestamp_ms=cursor_ms,
            )

            # Record in stats
            self.stats.all_path_results.append(result)
            if result.success:
                self.stats.total_paths_succeeded += 1
                paths_this_run += 1
                state.mark_done(make_path_key(path))
                self.stats.paths_by_type[path.type] = (
                    self.stats.paths_by_type.get(path.type, 0) + 1
                )
                self.stats.total_paths_completed += 1
                # Persist after every success so a crash doesn't lose progress
                state.save()
            else:
                self.stats.total_paths_failed += 1
                self.stats.failed_paths.append(result)

            # Structured twin of the log line above, for the web UI's
            # per-lesson view. No-op unless ROSETTA_EVENTS is set.
            events.emit(
                "path_done",
                ok=result.success,
                course=path.course,
                unit=path.unit_index,
                lesson=path.lesson_index,
                path_type=path.type,
                index=idx + 1,
                total=len(prepared),
                done_total=state.total_done(),
            )

            # Inter-path delay (human mode only; skipped after the last path)
            if self.human_mode and idx < len(prepared) - 1:
                delay_ms = random.randint(
                    self.inter_path_delay_min_ms,
                    self.inter_path_delay_max_ms,
                )
                self.logger.debug(f"    Waiting {delay_ms}ms before next path...")
                await asyncio.sleep(delay_ms / 1000.0)

        # Final save and summary
        state.save()
        self.stats.units_completed = sorted(
            self._derive_completed_units(course_menu, state)
        )
        self.logger.info(
            f"Units fully completed (state + Rosetta): {self.stats.units_completed}"
        )
        remaining_in_course = max(0, total_eligible - state.total_done())
        self.logger.info(
            f"This run: completed {paths_this_run} paths, "
            f"{state.total_done()} total done in state, "
            f"{remaining_in_course} remaining in course; "
            "resume on next run."
        )
        self.logger.info(
            f"Foundations batch finished. "
            f"Attempted={self.stats.total_paths_completed}, "
            f"Succeeded={self.stats.total_paths_succeeded}, "
            f"Failed={self.stats.total_paths_failed}"
        )
        return self.stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _collect_batch(
        self,
        course_menu,
        state: RunProgressState,
        budget: int | None,
    ) -> list[RosettaPath]:
        """
        Walk the course menu and collect up to *budget* paths to submit this
        run, skipping paths already recorded in state or removed by filters.

        A *budget* of ``None`` means unlimited (fast mode): collect every
        eligible, not-yet-done path.
        """
        batch: list[RosettaPath] = []

        def _full() -> bool:
            return budget is not None and len(batch) >= budget

        for unit in course_menu.units:
            if _full():
                break

            if not self.content_filter.should_process_unit(unit):
                continue

            for lesson in unit.lessons:
                if _full():
                    break

                if not self.content_filter.should_process_lesson(lesson):
                    continue

                for path in lesson.paths:
                    if _full():
                        break

                    if not self.content_filter.should_process_path(path):
                        self.stats.total_paths_skipped += 1
                        continue

                    if state.is_done(make_path_key(path)):
                        # Already recorded in state — resume past it silently
                        self.stats.total_paths_skipped += 1
                        continue

                    if self.content_filter.force_recomplete and path.complete:
                        self.logger.info(
                            f"    FORCE RE-COMPLETING {path.type} (was marked complete)"
                        )
                    elif path.complete and path.percent_complete < 100:
                        self.logger.info(
                            f"    Processing {path.type}: {path.percent_complete}% complete"
                        )

                    batch.append(path)

        return batch

    def _record_batch_stats(self, batch: list[RosettaPath]) -> None:
        """Record how many distinct units/lessons this run's batch touches."""
        self.stats.total_units_processed = len({p.unit_index for p in batch})
        self.stats.total_lessons_processed = len(
            {(p.unit_index, p.lesson_index) for p in batch}
        )

    def _derive_completed_units(
        self, course_menu, state: RunProgressState
    ) -> set[int]:
        """
        Return the unit numbers whose every path is done.

        A path counts as done when it is recorded in the persisted state
        (completed by this bot, possibly across several runs) or when Rosetta
        already reports it 100% complete. State is the source of truth, so the
        result is cumulative rather than per-session.
        """
        completed: set[int] = set()
        for unit in course_menu.units:
            paths = [p for lesson in unit.lessons for p in lesson.paths]
            if not paths:
                continue
            if all(
                state.is_done(make_path_key(p))
                or (p.complete and p.percent_complete >= 100)
                for p in paths
            ):
                completed.add(unit.unit_number)
        return completed

    def _count_eligible_paths(self, course_menu, state: RunProgressState) -> int:
        """Count paths that pass content filters (regardless of state)."""
        count = 0
        for unit in course_menu.units:
            if not self.content_filter.should_process_unit(unit):
                continue
            for lesson in unit.lessons:
                if not self.content_filter.should_process_lesson(lesson):
                    continue
                for path in lesson.paths:
                    if self.content_filter.should_process_path(path):
                        count += 1
        return count

    async def _complete_path(
        self,
        path: RosettaPath,
        session_token: str,
        school_id: str,
        user_id: str,
        duration_ms: int,
        questions_correct: int,
        questions_incorrect: int,
        timestamp_ms: int,
    ) -> PathScoreResult:
        """Complete a single path using precomputed duration/score/timestamp."""
        self.logger.info(
            f"    Completing path: {path.type} "
            f"(Course: {path.course}, Unit: {path.unit_index}, "
            f"Lesson: {path.lesson_index})"
        )

        return await self.api_port.update_path_score(
            session_token=session_token,
            school_id=school_id,
            user_id=user_id,
            course=path.course,
            # The course menu numbers units globally (0-19 across all 5 levels),
            # but each `course` (SK-ENG-L{1..5}) is a standalone level with only
            # 4 units. The path_scores endpoint expects the per-course unit index
            # (0-3), so reduce the global index mod 4. Without this, only Level 1
            # (units 0-3) registers; L2-L5 write to nonexistent coordinates and
            # never reflect as real progress in Rosetta.
            unit_index=path.unit_index % 4,
            lesson_index=path.curriculum_lesson_index,
            path_type=path.type,
            score_correct=questions_correct,
            score_incorrect=questions_incorrect,
            duration_ms=duration_ms,
            timestamp_ms=timestamp_ms,
            num_challenges=path.num_challenges,
        )
