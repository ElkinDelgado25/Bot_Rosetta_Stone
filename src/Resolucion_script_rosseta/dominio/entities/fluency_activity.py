from dataclasses import dataclass, field
from typing import List

from Resolucion_script_rosseta.dominio.entities.fluency_step import FluencyStep


@dataclass
class FluencyActivity:
    """An activity within a Fluency Builder lesson (sequence)."""

    activity_id: str
    activity_type: str
    interaction: str
    ordering: str
    steps: List[FluencyStep] = field(default_factory=list)

