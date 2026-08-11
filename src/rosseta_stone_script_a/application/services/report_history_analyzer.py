import re
from pathlib import Path
from typing import List, Set

from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin


class ReportHistoryAnalyzer(LoggingMixin):
    """Service for analyzing historical completion reports."""

    def __init__(self, reports_dir: Path = None):
        self.reports_dir = reports_dir or Path("logs/user_data")

    def get_safe_name(self, user_name: str | None) -> str:
        """Generate a safe filename prefix from user name."""
        if user_name:
            safe_name = re.sub(r"[^\w\s-]", "", user_name)
            safe_name = re.sub(r"\s+", "_", safe_name).strip("_")
            return safe_name
        return "unknown_user"

    def get_previous_reports(self, safe_name: str) -> List[Path]:
        """Find all previous reports for a user."""
        if not self.reports_dir.exists():
            return []
        pattern = f"{safe_name}_*.txt"
        return sorted(self.reports_dir.glob(pattern))

    def extract_completed_units_from_report(self, report_path: Path) -> Set[int]:
        """Extract completed units from a previous report."""
        completed_units = set()
        try:
            content = report_path.read_text(encoding="utf-8")
            # Match both the current label and the legacy one so old reports
            # keep contributing to history.
            match = re.search(
                r"Units (?:Fully Completed \(cumulative\)|Completed \(this session\)):"
                r"\s*\[([^\]]+)\]",
                content,
            )
            if match:
                units_str = match.group(1)
                for unit in units_str.split(","):
                    unit = unit.strip()
                    if unit.isdigit():
                        completed_units.add(int(unit))
        except Exception as e:
            self.logger.warning(f"Could not read previous report {report_path}: {e}")
        return completed_units

    def get_all_historically_completed_units(self, safe_name: str) -> Set[int]:
        """Get all units completed across all previous reports for this user."""
        all_completed = set()
        previous_reports = self.get_previous_reports(safe_name)
        for report_path in previous_reports:
            completed = self.extract_completed_units_from_report(report_path)
            all_completed.update(completed)
            self.logger.debug(f"From {report_path.name}: found units {completed}")
        return all_completed
