"""Tests for FluencyDurationCalculator — budgeted, jittered durations."""

from Resolucion_script_rosseta.aplicacion.services.fluency_duration_calculator import (
    FluencyDurationCalculator,
)


class TestFluencyDurationCalculator:
    def test_total_budget_reflects_configured_hours(self):
        calc = FluencyDurationCalculator(total_course_hours=1.0)
        assert calc.total_course_ms == 3_600_000

    def test_lesson_budget_splits_total_across_lessons_within_jitter(self):
        calc = FluencyDurationCalculator(total_course_hours=10.0)
        expected = calc.total_course_ms // 5
        budget = calc.lesson_budget_ms(5)
        assert expected * 2 // 3 <= budget <= expected * 4 // 3

    def test_lesson_budget_is_zero_for_no_lessons(self):
        calc = FluencyDurationCalculator(total_course_hours=10.0)
        assert calc.lesson_budget_ms(0) == 0

    def test_step_durations_returns_one_entry_per_step(self):
        calc = FluencyDurationCalculator(total_course_hours=10.0)
        durations = calc.step_durations_ms(600_000, 20)
        assert len(durations) == 20
        assert all(d >= 1500 for d in durations)

    def test_step_durations_empty_for_no_steps(self):
        calc = FluencyDurationCalculator(total_course_hours=10.0)
        assert calc.step_durations_ms(600_000, 0) == []

    def test_step_durations_respects_floor_on_tiny_budgets(self):
        calc = FluencyDurationCalculator(total_course_hours=10.0)
        durations = calc.step_durations_ms(10, 50)
        assert all(d >= 1500 for d in durations)

