from dataclasses import dataclass
from typing import List
from rosseta_stone_script_a.domain.entities.unit import Unit


@dataclass
class CourseMenu:
    current_course_id: str
    units: List[Unit]
