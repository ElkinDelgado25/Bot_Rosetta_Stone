from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ExamOption:
    """A single selectable option in an exam step."""
    id: str
    text: Optional[str] = None
    audio_uri: Optional[str] = None


@dataclass
class ExamStep:
    """A step within an exam activity."""
    activity_step_id: str
    step_type: str  # e.g., "multipleChoice"
    prompt: str = ""
    passage_html: Optional[str] = None
    audio_uri: Optional[str] = None
    options: List[ExamOption] = field(default_factory=list)
    instructions: Optional[str] = None


@dataclass
class ExamActivity:
    """An activity consisting of one or more steps."""
    activity_id: str
    activity_type: str  # e.g., "RightWordWQuestionWAnswers", "WTextWQuestionWAnswers"
    interaction: str = "test"
    skills: Dict[str, Any] = field(default_factory=dict)
    steps: List[ExamStep] = field(default_factory=list)
    instructions: Optional[str] = None


@dataclass
class ExamAnswer:
    """An answer for an activity step."""
    activity_step_id: str
    content_id: str


@dataclass
class ExamProgress:
    """Current progress in the exam."""
    question_no: int
    no_of_questions: int
    section: int
    tally: Optional[Any] = None
    ability: Optional[float] = None
    standard_error: Optional[float] = None


@dataclass
class ExamScore:
    """Final or intermediate score of the exam."""
    score: int
    max_score: int
    cefr: str
    ilr: Optional[str] = None
    clb: Optional[str] = None
    warning: Optional[str] = None


@dataclass
class ExamStepResult:
    """Response returned after submitting an assessment step."""
    assessment_name: str
    form_number: int
    activity: Optional[ExamActivity] = None
    progress: Optional[ExamProgress] = None
    score: Optional[ExamScore] = None
    is_complete: bool = False
