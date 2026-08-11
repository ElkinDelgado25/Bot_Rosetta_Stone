from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from rosseta_stone_script_a.domain.entities.completion_stats import CompletionStats
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin

# Total units in Rosetta Stone Foundations
TOTAL_UNITS = 20


class ReportGenerator(LoggingMixin):
    """Service for generating completion reports."""

    def __init__(self, output_dir: Path = None):
        self.output_dir = output_dir or Path("logs/user_data")

    async def generate_report(
        self,
        user_name: str | None,
        stats: CompletionStats,
        captured_data: Dict[str, Any],
        historically_completed: set[int],
    ) -> Path:
        """
        Generate a completion report with user info and statistics.

        Args:
            user_name: Name of the user
            stats: Completion statistics for this session
            captured_data: Captured session data
            historically_completed: Set of previously completed units

        Returns:
            Path to the generated report file
        """
        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename with user name
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = self._get_safe_name(user_name)
        file_name = f"{safe_name}_{timestamp}.txt"
        file_path = self.output_dir / file_name

        # Units fully complete per persisted state (cumulative across runs)
        current_completed = set(stats.units_completed)

        # All completed units (history + current)
        all_completed = historically_completed.union(current_completed)

        # Calculate pending units
        all_units = set(range(1, TOTAL_UNITS + 1))
        pending_units = sorted(all_units - all_completed)

        # Build and write report
        report_content = self._build_report_content(
            user_name=user_name,
            stats=stats,
            captured_data=captured_data,
            historically_completed=historically_completed,
            all_completed=all_completed,
            pending_units=pending_units,
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        self.logger.info(f"Completion report saved to {file_path}")

        # Write a separate failures dump if there were any
        if stats.failed_paths:
            failures_path = self.output_dir / f"{safe_name}_{timestamp}_failures.txt"
            failures_content = self._build_failures_content(stats)
            with open(failures_path, "w", encoding="utf-8") as f:
                f.write(failures_content)
            self.logger.warning(
                f"Wrote {len(stats.failed_paths)} path-score failures to {failures_path}"
            )

        # Write a full attempts audit (every path_score call, success or fail)
        if stats.all_path_results:
            attempts_path = self.output_dir / f"{safe_name}_{timestamp}_attempts.csv"
            attempts_content = self._build_attempts_csv(stats)
            with open(attempts_path, "w", encoding="utf-8", newline="") as f:
                f.write(attempts_content)
            self.logger.info(
                f"Wrote {len(stats.all_path_results)} path-score attempts to {attempts_path}"
            )

        return file_path

    def _get_safe_name(self, user_name: str | None) -> str:
        """Generate a safe filename prefix from user name."""
        import re

        if user_name:
            safe_name = re.sub(r"[^\w\s-]", "", user_name)
            safe_name = re.sub(r"\s+", "_", safe_name).strip("_")
            return safe_name
        return "unknown_user"

    def _build_report_content(
        self,
        user_name: str | None,
        stats: CompletionStats,
        captured_data: Dict[str, Any],
        historically_completed: set[int],
        all_completed: set[int],
        pending_units: list[int],
    ) -> str:
        """Build the report content as a formatted string."""
        # Get credentials
        credentials = captured_data.get("credentials", {})
        email = credentials.get("email", "N/A")

        # Build report lines
        report_lines = [
            "=" * 60,
            "ROSETTA STONE - COMPLETION REPORT",
            "=" * 60,
            "",
            "USER INFORMATION",
            "-" * 40,
            f"  Name: {user_name or 'Unknown'}",
            f"  User ID: {captured_data.get('user_id', 'N/A')}",
            f"  School ID: {captured_data.get('school_id', 'N/A')}",
            f"  Language: {captured_data.get('lang_code', 'N/A')}",
            "",
            "ACCOUNT",
            "-" * 40,
            f"  Email: {email}",
            "",
            "SESSION INFORMATION",
            "-" * 40,
            f"  Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "COMPLETION STATISTICS (THIS SESSION)",
            "-" * 40,
            f"  Units Processed: {stats.total_units_processed}",
            f"  Units Fully Completed (cumulative): {sorted(stats.units_completed)}",
            f"  Lessons Processed: {stats.total_lessons_processed}",
            f"  Paths Attempted: {stats.total_paths_completed}",
            f"  Paths Succeeded (API 2xx): {stats.total_paths_succeeded}",
            f"  Paths Failed (API non-2xx / exception): {stats.total_paths_failed}",
            f"  Paths Skipped (already done): {stats.total_paths_skipped}",
            "",
            "HISTORICAL PROGRESS",
            "-" * 40,
            f"  Previously Completed Units: {sorted(historically_completed) if historically_completed else 'None'}",
            f"  All Completed Units (total): {sorted(all_completed)}",
            f"  Total Units Completed: {len(all_completed)} / {TOTAL_UNITS}",
            "",
            "PENDING UNITS",
            "-" * 40,
            f"  Units Still Pending: {pending_units if pending_units else 'None - All Complete!'}",
            f"  Total Pending: {len(pending_units)} / {TOTAL_UNITS}",
            "",
            "PATHS BY TYPE",
            "-" * 40,
        ]

        # Add paths by type
        for path_type, count in sorted(stats.paths_by_type.items()):
            report_lines.append(f"  {path_type}: {count}")

        if stats.errors:
            report_lines.extend(
                [
                    "",
                    "ERRORS",
                    "-" * 40,
                ]
            )
            for error in stats.errors:
                report_lines.append(f"  - {error}")

        if stats.failed_paths:
            report_lines.extend(
                [
                    "",
                    "FAILED PATH SCORES (summary — see _failures.txt for detail)",
                    "-" * 40,
                ]
            )
            failures_by_status: Dict[Any, int] = {}
            failures_by_unit: Dict[Any, int] = {}
            for fp in stats.failed_paths:
                failures_by_status[fp.status] = failures_by_status.get(fp.status, 0) + 1
                failures_by_unit[fp.unit_index] = (
                    failures_by_unit.get(fp.unit_index, 0) + 1
                )
            for status, count in sorted(failures_by_status.items()):
                report_lines.append(f"  HTTP {status}: {count}")
            report_lines.append("")
            report_lines.append("  Failed-path counts by unit_index sent to API:")
            for unit_idx, count in sorted(failures_by_unit.items()):
                report_lines.append(f"    unit_index={unit_idx}: {count}")

        report_lines.extend(
            [
                "",
                "=" * 60,
                "END OF REPORT",
                "=" * 60,
            ]
        )

        return "\n".join(report_lines)

    def _build_attempts_csv(self, stats: CompletionStats) -> str:
        """Build a CSV of every path_score attempt (success and failure)."""
        import csv
        import io

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "course",
                "unit_index_sent",
                "lesson_index_sent",
                "path_type",
                "success",
                "http_status",
                "error",
                "response_body_snippet",
            ]
        )
        for r in stats.all_path_results:
            snippet = (r.response_body or "").replace("\n", " ").replace("\r", " ")[:200]
            writer.writerow(
                [
                    r.course,
                    r.unit_index,
                    r.lesson_index,
                    r.path_type,
                    "1" if r.success else "0",
                    r.status,
                    r.error,
                    snippet,
                ]
            )
        return buf.getvalue()

    def _build_failures_content(self, stats: CompletionStats) -> str:
        """Build a detailed dump of every failed path_score call."""
        lines = [
            "=" * 60,
            "ROSETTA STONE - PATH SCORE FAILURES",
            "=" * 60,
            f"Total failures: {len(stats.failed_paths)}",
            "",
        ]
        for i, fp in enumerate(stats.failed_paths, start=1):
            lines.extend(
                [
                    f"[{i}] {fp.course} unit_index={fp.unit_index} "
                    f"lesson_index={fp.lesson_index} path_type={fp.path_type}",
                    f"    HTTP status: {fp.status}",
                ]
            )
            if fp.error:
                lines.append(f"    error: {fp.error}")
            if fp.response_body:
                snippet = fp.response_body.replace("\n", " ")[:500]
                lines.append(f"    body: {snippet}")
            lines.append("")
        return "\n".join(lines)
