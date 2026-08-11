import asyncio
from typing import Any, Dict

from rosseta_stone_script_a.application.ports.orchestrator import OrchestratorPort
from rosseta_stone_script_a.application.ports.web import IWebSession
from rosseta_stone_script_a.application.services.fluency_session_capturer import (
    FluencySessionCapturer,
)
from rosseta_stone_script_a.application.services.rosetta_session_capturer import (
    RosettaSessionCapturer,
)
from rosseta_stone_script_a.application.use_cases.go_to_foundations import (
    GoToFundationsUseCase,
)
from rosseta_stone_script_a.application.use_cases.login_rosseta import (
    LoginRossetaUseCase,
)
from rosseta_stone_script_a.domain.entities.credentials import Credentials
from rosseta_stone_script_a.domain.values.rosetta_product import RosettaProduct


class OpenFundations(OrchestratorPort):
    """
    Orchestrator that composes login and navigation to Foundations.

    Workflow:
    1. Login to Rosetta Stone
    2. Navigate to Foundations workspace
    """

    # Configuration for session capture waiting
    MAX_CAPTURE_WAIT_SECONDS = 15
    CAPTURE_POLL_INTERVAL_SECONDS = 0.5

    def __init__(
        self,
        login_use_case: LoginRossetaUseCase,
        navigate_use_case: GoToFundationsUseCase,
        web_session: IWebSession,
        session_capturer: RosettaSessionCapturer,
        fluency_capturer: FluencySessionCapturer | None = None,
    ):
        super().__init__()
        self.login_use_case = login_use_case
        self.navigate_use_case = navigate_use_case
        self.web_session = web_session
        self.session_capturer = session_capturer
        self.fluency_capturer = fluency_capturer or FluencySessionCapturer()

    async def execute(self, credentials: Credentials) -> Dict[str, Any]:
        """
        Execute the OpenFoundations workflow.

        Args:
            credentials: User credentials for login

        Returns:
            Dict[str, Any]: Captured session data
        """
        self.logger.info("Starting product entry workflow")

        # Start network interception BEFORE login to capture all auth tokens.
        # We register both capturers because the product is not yet known: the
        # Foundations one harvests tracking. tokens, the Fluency one harvests the
        # gaia authorization header. Only the matching one will complete.
        monitor = self.web_session.network_monitor
        if monitor:
            self.logger.info("Starting network interception for session capture")
            monitor.add_request_listener(self.session_capturer.handle_request)
            monitor.add_request_listener(self.fluency_capturer.handle_request)
        else:
            self.logger.warning("Network monitor not available for session capture")

        # Step 1: Login to Rosetta Stone
        await self.login_use_case.execute(credentials)

        # Step 2: Detect the product and navigate into it
        await self.navigate_use_case.execute()
        product = self.navigate_use_case.product

        # Step 3: Wait for the session data the detected product needs
        if product == RosettaProduct.FLUENCY_BUILDER:
            await self._wait_for_capture(
                self.fluency_capturer, "Fluency Builder (gaia)"
            )
            captured_data = dict(self.fluency_capturer.get_captured_data())
        else:
            await self._wait_for_capture(self.session_capturer, "Foundations")
            captured_data = dict(self.session_capturer.get_captured_data())

        # Stop network interception
        if monitor:
            monitor.remove_request_listener(self.session_capturer.handle_request)
            monitor.remove_request_listener(self.fluency_capturer.handle_request)

        # Log field names only. Session values can contain authorization tokens.
        self.logger.info(
            "Captured session fields: %s", ", ".join(sorted(captured_data))
        )

        # Enrich captured data
        captured_data["product"] = product.value
        captured_data["user_name"] = self.navigate_use_case.user_name
        captured_data["credentials"] = {
            "email": str(credentials.email),
        }

        self.logger.info(f"Product entry workflow completed ({product.value})")
        return captured_data

    async def _wait_for_capture(self, capturer, label: str) -> None:
        """Poll until ``capturer.is_complete()`` or the timeout elapses."""
        self.logger.info(f"Waiting for {label} session capture to complete...")

        elapsed = 0.0
        while elapsed < self.MAX_CAPTURE_WAIT_SECONDS:
            if capturer.is_complete():
                self.logger.info(
                    f"{label} session data captured after {elapsed:.1f}s"
                )
                return

            await asyncio.sleep(self.CAPTURE_POLL_INTERVAL_SECONDS)
            elapsed += self.CAPTURE_POLL_INTERVAL_SECONDS

        missing = (
            capturer.get_missing_keys()
            if hasattr(capturer, "get_missing_keys")
            else "unknown"
        )
        self.logger.warning(
            f"{label} session capture timeout "
            f"({self.MAX_CAPTURE_WAIT_SECONDS}s). Missing data: {missing}"
        )
