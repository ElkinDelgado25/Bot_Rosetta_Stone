from dataclasses import dataclass


@dataclass
class PathScoreResult:
    """Outcome of a single path_score API call."""

    success: bool
    status: int
    course: str
    unit_index: int
    lesson_index: int
    path_type: str
    response_body: str = ""
    error: str = ""
