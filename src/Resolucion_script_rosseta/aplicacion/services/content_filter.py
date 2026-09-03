from typing import List

from Resolucion_script_rosseta.dominio.entities.lesson import Lesson
from Resolucion_script_rosseta.dominio.entities.path import Path
from Resolucion_script_rosseta.dominio.entities.unit import Unit
from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin


class ContentFilter(LoggingMixin):
    """Service for filtering units, lessons, and paths based on configuration."""

    def __init__(
        self,
        units_to_complete: List[int] = None,
        lessons_to_complete: List[int] = None,
        path_types_to_complete: List[str] = None,
        force_recomplete: bool = False,
    ):
        self.units_to_complete = units_to_complete or []
        self.lessons_to_complete = lessons_to_complete or []
        self.path_types_to_complete = path_types_to_complete or []
        self.force_recomplete = force_recomplete

    def should_process_unit(self, unit: Unit) -> bool:
        """Check if a unit should be processed based on configuration."""
        if not self.units_to_complete:
            return True
        return unit.unit_number in self.units_to_complete

    def should_process_lesson(self, lesson: Lesson) -> bool:
        """Check if a lesson should be processed based on configuration."""
        if not self.lessons_to_complete:
            return True
        return lesson.lesson_number in self.lessons_to_complete

    def should_process_path(self, path: Path) -> bool:
        """Check if a path should be processed based on configuration and completion status."""
        # Check path type filter first
        if self.path_types_to_complete and path.type not in self.path_types_to_complete:
            return False

        # If force_recomplete is enabled, process even if marked as complete
        if self.force_recomplete:
            return True

        # Skip if already 100% complete (and not forcing)
        if path.complete and path.percent_complete >= 100:
            return False

        return True

    def log_skip_reason(
        self, item_type: str, item_identifier: str | int, reason: str
    ) -> None:
        """Log why an item was skipped."""
        self.logger.debug(f"Skipping {item_type} {item_identifier} ({reason})")

