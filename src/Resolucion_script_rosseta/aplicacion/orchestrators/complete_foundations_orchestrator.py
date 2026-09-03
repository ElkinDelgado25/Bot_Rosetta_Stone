from pathlib import Path
from typing import Any, Dict

from Resolucion_script_rosseta.aplicacion.ports.orchestrator import OrchestratorPort
from Resolucion_script_rosseta.aplicacion.services.report_generator import (
    ReportGenerator,
)
from Resolucion_script_rosseta.aplicacion.services.report_history_analyzer import (
    ReportHistoryAnalyzer,
)
from Resolucion_script_rosseta.aplicacion.use_cases.complete_foundations import (
    CompleteFoundationsUseCase,
)
from Resolucion_script_rosseta.dominio.entities.completion_stats import CompletionStats
from Resolucion_script_rosseta.dominio.errors import SessionCaptureIncomplete


class CompleteFoundationsOrchestrator(OrchestratorPort):
    """
    Orchestrator that handles the completion of Foundations lessons.
    """

    def __init__(self, complete_foundations_use_case: CompleteFoundationsUseCase):
        super().__init__()
        self.complete_foundations_use_case = complete_foundations_use_case
        self.output_dir = Path("logs/user_data")

        # Initialize services
        self.report_generator = ReportGenerator(self.output_dir)
        self.history_analyzer = ReportHistoryAnalyzer(self.output_dir)

    async def execute(self, captured_data: Dict[str, Any]) -> None:
        """
        Execute the completion workflow using captured session data.

        Args:
            captured_data: Data captured from the session (tokens, ids, user_name, account email, etc.)
        """
        user_name = captured_data.get("user_name")

        # Check required session data (excluding user_name which is optional for report)
        required_keys = [
            "authorization",
            "lang_code",
            "session_token",
            "school_id",
            "user_id",
        ]
        missing_keys = [k for k in required_keys if not captured_data.get(k)]

        if missing_keys:
            # Loud on purpose. Returning here used to leave the process exiting
            # 0 after sending nothing, which reads as success everywhere.
            self.logger.error(
                f"Missing captured session data: {missing_keys}. Nothing was sent."
            )
            raise SessionCaptureIncomplete(missing_keys, product="Foundations")

        self.logger.info("Session data captured successfully. Starting completion...")
        email = (captured_data.get("credentials") or {}).get("email")
        stats = await self.complete_foundations_use_case.execute(
            authorization=captured_data["authorization"],
            language_code=captured_data["lang_code"],
            session_token=captured_data["session_token"],
            school_id=captured_data["school_id"],
            user_id=captured_data["user_id"],
            email=email,
        )

        # Generate completion report using services
        safe_name = self.history_analyzer.get_safe_name(user_name)
        historically_completed = (
            self.history_analyzer.get_all_historically_completed_units(safe_name)
        )
        self.logger.info(
            f"Previously completed units (from history): {sorted(historically_completed)}"
        )

        await self.report_generator.generate_report(
            user_name=user_name,
            stats=stats,
            captured_data=captured_data,
            historically_completed=historically_completed,
        )

