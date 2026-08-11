from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FluencySequenceRef:
    """A lesson reference inside the catalog: identity, title and progress.

    Shallow view from ``getCoursesAndProgress`` — no activities. ``percent_complete``
    is a fraction in [0.0, 1.0] (1.0 == fully complete), joined from the separate
    ``progress`` root field by sequence id; a lesson with no progress entry stays
    at 0.0.
    """

    sequence_id: str
    title: Optional[str]
    percent_complete: float = 0.0


@dataclass
class FluencyCourse:
    """A course assigned to the user in Fluency Builder."""

    course_id: str
    product_id: Optional[str]
    title: Optional[str]
    cefr: Optional[str]
    topic: Optional[str]
    sequences: List[FluencySequenceRef] = field(default_factory=list)
