from dataclasses import dataclass
from typing import List
from rosseta_stone_script_a.domain.entities.lesson import Lesson


@dataclass
class Unit:
    id: str
    index: int
    unit_number: int
    lessons: List[Lesson]
