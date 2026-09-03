from dataclasses import dataclass, field
from typing import List


@dataclass
class FluencyStep:
    """A single step within a Fluency Builder activity.

    ``correct_answer_ids`` holds the option ids the platform marks as correct
    (from the ``correct`` field of the content tree). It is empty for read-only
    steps such as vocabulary/grammar cards, which have no answer to grade.
    """

    step_id: str
    type: str
    correct_answer_ids: List[str] = field(default_factory=list)
