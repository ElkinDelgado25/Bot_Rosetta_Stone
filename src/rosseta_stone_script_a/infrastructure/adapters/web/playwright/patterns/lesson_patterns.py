"""
Lesson-specific patterns for Foundations flows.
"""

from dataclasses import dataclass

from rosseta_stone_script_a.shared.utils.compile_case_insensitive import (
    compile_case_insensitive,
)

cci = compile_case_insensitive


@dataclass(frozen=True)
class LessonPatterns:
    """Patterns for lesson management and navigation."""

    # Foundations navigation
    FOUNDATIONS = cci(r"foundations|fundamentos")

    # Fluency Builder is a different Rosetta Stone product with its own backend
    # and content model. It is not supported; detected only to fail with a clear
    # message instead of a misleading "selector not found".
    FLUENCY_BUILDER = cci(r"fluency\s*builder")



    LAUNCH_COURSE_BUTTON = "LaunchCourseButton"
