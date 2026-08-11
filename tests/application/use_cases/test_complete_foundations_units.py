"""Unit-progress derivation tests for CompleteFoundationsUseCase.

Regression for the batch-mode refactor that stopped populating
``stats.units_completed`` / ``stats.total_units_processed``, which made every
report claim 0/20 units completed even after successful runs.
"""

from pathlib import Path

import pytest

from rosseta_stone_script_a.application.use_cases.complete_foundations import (
    CompleteFoundationsUseCase,
)
from rosseta_stone_script_a.domain.entities.course_menu import CourseMenu as _CourseMenu
from rosseta_stone_script_a.domain.entities.lesson import Lesson
from rosseta_stone_script_a.domain.entities.path import Path as RosettaPath
from rosseta_stone_script_a.domain.entities.unit import Unit
from rosseta_stone_script_a.infrastructure.state import (
    RunProgressState,
    make_path_key,
)


def CourseMenu(units: list[Unit]) -> _CourseMenu:
    return _CourseMenu(current_course_id="course-1", units=units)


def _path(
    unit_index: int,
    lesson_index: int,
    path_type: str,
    complete: bool = False,
    percent: int = 0,
) -> RosettaPath:
    return RosettaPath(
        unit_index=unit_index,
        lesson_index=lesson_index,
        curriculum_lesson_index=lesson_index,
        type=path_type,
        course="SK-ENG-L1-NA-PE-NA-NA-Y-3",
        num_challenges=10,
        time_estimate=300,
        complete=complete,
        percent_complete=percent,
    )


def _unit(unit_number: int, unit_index: int, paths: list[RosettaPath]) -> Unit:
    lesson = Lesson(
        id=f"lesson-{unit_index}-0",
        index=0,
        lesson_number=1,
        paths=paths,
    )
    return Unit(
        id=f"unit-{unit_index}",
        index=unit_index,
        unit_number=unit_number,
        lessons=[lesson],
    )


@pytest.fixture
def use_case(tmp_path: Path) -> CompleteFoundationsUseCase:
    return CompleteFoundationsUseCase(api_port=None, state_dir=tmp_path)


@pytest.fixture
def state(tmp_path: Path) -> RunProgressState:
    return RunProgressState(tmp_path / "state.json")


class TestDeriveCompletedUnits:
    def test_unit_with_all_paths_in_state_is_completed(self, use_case, state):
        paths = [_path(0, 0, "general"), _path(0, 0, "vocabulary")]
        for p in paths:
            state.mark_done(make_path_key(p))
        menu = CourseMenu(units=[_unit(1, 0, paths)])

        assert use_case._derive_completed_units(menu, state) == {1}

    def test_unit_with_pending_path_is_not_completed(self, use_case, state):
        done = _path(0, 0, "general")
        pending = _path(0, 0, "vocabulary")
        state.mark_done(make_path_key(done))
        menu = CourseMenu(units=[_unit(1, 0, [done, pending])])

        assert use_case._derive_completed_units(menu, state) == set()

    def test_path_already_complete_on_rosetta_counts_as_done(self, use_case, state):
        in_state = _path(0, 0, "general")
        on_rosetta = _path(0, 0, "vocabulary", complete=True, percent=100)
        state.mark_done(make_path_key(in_state))
        menu = CourseMenu(units=[_unit(1, 0, [in_state, on_rosetta])])

        assert use_case._derive_completed_units(menu, state) == {1}

    def test_partially_complete_rosetta_path_does_not_count(self, use_case, state):
        partial = _path(0, 0, "general", complete=True, percent=60)
        menu = CourseMenu(units=[_unit(1, 0, [partial])])

        assert use_case._derive_completed_units(menu, state) == set()

    def test_empty_unit_is_ignored(self, use_case, state):
        empty_unit = Unit(id="unit-0", index=0, unit_number=1, lessons=[])
        menu = CourseMenu(units=[empty_unit])

        assert use_case._derive_completed_units(menu, state) == set()

    def test_multiple_units_report_their_unit_numbers(self, use_case, state):
        unit1_paths = [_path(0, 0, "general")]
        unit5_paths = [_path(4, 0, "general")]
        for p in unit1_paths + unit5_paths:
            state.mark_done(make_path_key(p))
        menu = CourseMenu(
            units=[_unit(1, 0, unit1_paths), _unit(5, 4, unit5_paths)]
        )

        assert use_case._derive_completed_units(menu, state) == {1, 5}


class TestBatchStats:
    def test_counts_distinct_units_and_lessons(self, use_case):
        batch = [
            _path(0, 0, "general"),
            _path(0, 0, "vocabulary"),
            _path(0, 1, "general"),
            _path(1, 0, "general"),
        ]

        use_case._record_batch_stats(batch)

        assert use_case.stats.total_units_processed == 2
        assert use_case.stats.total_lessons_processed == 3

    def test_empty_batch_counts_zero(self, use_case):
        use_case._record_batch_stats([])

        assert use_case.stats.total_units_processed == 0
        assert use_case.stats.total_lessons_processed == 0
