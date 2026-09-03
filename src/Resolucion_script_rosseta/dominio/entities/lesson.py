from dataclasses import dataclass
from typing import List
from Resolucion_script_rosseta.dominio.entities.path import Path


@dataclass
class Lesson:
    id: str
    index: int
    lesson_number: int
    paths: List[Path]

