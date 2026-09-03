from dataclasses import dataclass, field
from typing import Dict, List

from Resolucion_script_rosseta.dominio.values.path_score_result import PathScoreResult


@dataclass
class CompletionStats:
    """Statistics about the completion process."""

    total_units_processed: int = 0
    total_lessons_processed: int = 0
    total_paths_completed: int = 0  # Attempted (kept name for back-compat in report)
    total_paths_succeeded: int = 0
    total_paths_failed: int = 0
    total_paths_skipped: int = 0  # Already completed
    units_completed: list = field(default_factory=list)
    paths_by_type: Dict[str, int] = field(default_factory=dict)
    errors: list = field(default_factory=list)
    failed_paths: List[PathScoreResult] = field(default_factory=list)
    all_path_results: List[PathScoreResult] = field(default_factory=list)

