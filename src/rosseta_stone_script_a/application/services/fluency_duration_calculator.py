"""Fabricates realistic per-step study durations for Fluency Builder.

Unlike Foundations, Fluency's content tree ships no per-item time estimate
(there is no Fluency equivalent of ``Path.time_estimate``). Mirror
Foundations' realism — ``PathCalculator`` jitters durations around a real
estimate — by budgeting a total course study time and dividing it, with
jitter, across however many lessons this run is about to complete. A full
Rosetta Stone level runs roughly 70 hours of study, so that is the default
budget.
"""

import random


class FluencyDurationCalculator:
    """Distributes a total course-duration budget across lessons and steps."""

    def __init__(self, total_course_hours: float = 70.0):
        self.total_course_ms = int(total_course_hours * 3600 * 1000)

    def lesson_budget_ms(self, lesson_count: int) -> int:
        """This lesson's share of the total budget, jittered +/-33%."""
        if lesson_count <= 0:
            return 0
        base = self.total_course_ms // lesson_count
        jitter = base // 3
        return base + (random.randint(-jitter, jitter) if jitter else 0)

    def step_durations_ms(self, lesson_budget_ms: int, step_count: int) -> list[int]:
        """Split one lesson's budget across its steps, each at least a realistic floor."""
        if step_count <= 0:
            return []
        floor_ms = 1500
        base = max(floor_ms, lesson_budget_ms // step_count)
        jitter = base // 3
        return [
            max(floor_ms, base + (random.randint(-jitter, jitter) if jitter else 0))
            for _ in range(step_count)
        ]
