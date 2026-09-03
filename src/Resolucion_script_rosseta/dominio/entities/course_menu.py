from dataclasses import dataclass
from typing import List
from Resolucion_script_rosseta.dominio.entities.unit import Unit


@dataclass
class CourseMenu:
    current_course_id: str
    units: List[Unit]

