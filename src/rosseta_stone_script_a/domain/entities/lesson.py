from dataclasses import dataclass
from typing import List
from rosseta_stone_script_a.domain.entities.path import Path


@dataclass
class Lesson:
    id: str
    index: int
    lesson_number: int
    paths: List[Path]
