from dataclasses import dataclass


@dataclass
class Path:
    unit_index: int
    lesson_index: int
    curriculum_lesson_index: int
    type: str
    course: str
    num_challenges: int
    time_estimate: int
    complete: bool
    percent_complete: int
