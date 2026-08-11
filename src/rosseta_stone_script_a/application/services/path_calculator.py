import math
import random
from dataclasses import dataclass

from rosseta_stone_script_a.domain.entities.path import Path


@dataclass
class PathCalculationResult:
    """Result of path time and score calculations."""

    time_in_milliseconds: int
    questions_correct: int
    questions_incorrect: int
    time_completed: int


class PathCalculator:
    """Service for calculating path completion times and scores."""

    def __init__(
        self,
        target_score_percent: int = 100,
        max_start_time_offset_ms: int = 432000000,
    ):
        self.target_score_percent = target_score_percent
        self.max_start_time_offset_ms = max_start_time_offset_ms

    def calculate_path_completion(
        self, path: Path, start_time: int, time_so_far: int
    ) -> PathCalculationResult:
        """
        Calculate completion data for a path.

        Args:
            path: The path to calculate for
            start_time: Session start time in milliseconds
            time_so_far: Accumulated time so far in milliseconds

        Returns:
            PathCalculationResult with calculated values
        """
        time_estimate = path.time_estimate
        time_in_minutes = time_estimate + random.randint(
            -1 * math.floor(time_estimate / 3), math.floor(time_estimate / 3)
        )
        time_in_milliseconds = time_in_minutes * 60000 + random.randint(0, 6000)

        percent_correct = self.target_score_percent
        questions_correct = math.ceil(path.num_challenges * (percent_correct / 100))
        questions_incorrect = path.num_challenges - questions_correct

        time_completed = start_time + time_so_far + time_in_milliseconds

        return PathCalculationResult(
            time_in_milliseconds=time_in_milliseconds,
            questions_correct=questions_correct,
            questions_incorrect=questions_incorrect,
            time_completed=time_completed,
        )

    def calculate_next_time_increment(self, time_estimate: int) -> int:
        """
        Calculate the time increment to add for the next path.

        Args:
            time_estimate: Estimated time for the path in minutes

        Returns:
            Time increment in milliseconds
        """
        time_in_minutes = time_estimate + random.randint(
            -1 * math.floor(time_estimate / 3), math.floor(time_estimate / 3)
        )
        time_in_milliseconds = time_in_minutes * 60000 + random.randint(0, 6000)
        return time_in_milliseconds + random.randint(0, 60000)
