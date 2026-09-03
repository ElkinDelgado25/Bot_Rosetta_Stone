from dataclasses import dataclass


@dataclass
class FluencyProgressResult:
    """Outcome of a single AddProgress mutation call (one activity's steps)."""

    success: bool
    status: int
    course_id: str = ""
    sequence_id: str = ""
    activity_id: str = ""
    message_count: int = 0
    response_body: str = ""
    error: str = ""
    rate_limited: bool = False
