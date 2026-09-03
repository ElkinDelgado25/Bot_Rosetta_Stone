from dataclasses import dataclass, field
from typing import List, Optional

from Resolucion_script_rosseta.dominio.entities.fluency_activity import FluencyActivity


@dataclass
class FluencySequence:
    """Full detail of one Fluency Builder lesson, from ``getSequence``.

    This is the deep tree used by the (future) write phase: it carries the
    activity/step ids and the correct-answer ids needed to fabricate progress.
    """

    sequence_id: str
    course_id: str
    title: Optional[str]
    version: Optional[int]
    activities: List[FluencyActivity] = field(default_factory=list)

