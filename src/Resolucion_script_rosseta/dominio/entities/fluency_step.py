from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class FluencyAnswer:
    """One answer option of a step, as the player renders it.

    ``text`` is what the choice card shows (joined from the content chunks);
    ``audio_sha`` is the sha1 that names the option audio on
    ``resources.rosettastone.com`` — the same sha the captured URL ends with,
    which is what lets the bot pick the card it must speak.
    """

    id: str
    text: str = ""
    audio_sha: Optional[str] = None


@dataclass
class FluencyStep:
    """A single step within a Fluency Builder activity.

    ``correct_answer_ids`` holds the option ids of the step (from the
    ``correct`` field of the content tree). For vocabulary cards it holds the
    carousel ``word`` ids when ``correct`` is absent.

    ``success_answer_ids`` is the accepted subset (``postProcess
    .successResponses``): in most conversation steps every option is accepted,
    but the closing steps of a dialogue accept only one — speaking any other
    aborts the walk and the platform marks the activity as skipped.

    ``answers`` are the rendered options with their text and audio sha.
    """

    step_id: str
    type: str
    correct_answer_ids: List[str] = field(default_factory=list)
    success_answer_ids: List[str] = field(default_factory=list)
    answers: List[FluencyAnswer] = field(default_factory=list)
