from dataclasses import dataclass, field
from typing import List

from Resolucion_script_rosseta.dominio.entities.fluency_course import FluencyCourse


@dataclass
class FluencyCatalog:
    """The user's Fluency Builder catalog: assigned courses with per-lesson progress.

    Equivalent of Foundations' ``CourseMenu`` — the "menu" that says what exists
    and what is still pending.
    """

    courses: List[FluencyCourse] = field(default_factory=list)

