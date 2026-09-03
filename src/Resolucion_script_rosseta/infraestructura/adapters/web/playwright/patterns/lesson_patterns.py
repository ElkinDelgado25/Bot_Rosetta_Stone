"""
Lesson-specific patterns for Foundations flows.
"""

from dataclasses import dataclass

from Resolucion_script_rosseta.compartido.utils.compile_case_insensitive import (
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

    # Exam / Placement / Screener assessment patterns
    EXAM = cci(r"assessment|screener|placement|examen|evaluaci[oó]n|diagn[oó]stico")

    LAUNCH_COURSE_BUTTON = "LaunchCourseButton"

