from dataclasses import dataclass
from typing import List
from Resolucion_script_rosseta.dominio.entities.lesson import Lesson


@dataclass
class Unit:
    id: str
    index: int
    unit_number: int
    lessons: List[Lesson]

