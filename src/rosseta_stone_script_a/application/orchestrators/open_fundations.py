import asyncio
from typing import Any, Dict

from rosseta_stone_script_a.application.ports.learner_dashboard import (
    LearnerDashboardPort,
)
from rosseta_stone_script_a.application.ports.orchestrator import OrchestratorPort
from rosseta_stone_script_a.application.ports.web import IWebSession
from rosseta_stone_script_a.application.services.fluency_session_capturer import (
    FluencySessionCapturer,
)
from rosseta_stone_script_a.application.services.learner_auth_capturer import (
    LearnerAuthCapturer,
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
from rosseta_stone_script_a.domain.errors import SessionCaptureIncomplete
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
        learner_auth_capturer: LearnerAuthCapturer | None = None,
        learner_dashboard: LearnerDashboardPort | None = None,
    ):
        super().__init__()
        self.login_use_case = login_use_case
        self.navigate_use_case = navigate_use_case
        self.web_session = web_session
        self.session_capturer = session_capturer
        self.fluency_capturer = fluency_capturer or FluencySessionCapturer()
        self.learner_auth_capturer = learner_auth_capturer or LearnerAuthCapturer()
        # Sin panel inyectado la corrida funciona igual; solo no se comprueba.
        self.learner_dashboard = learner_dashboard

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
            # Las credenciales del panel del aprendiz viajan en el *cuerpo* de
            # la respuesta del login, no en cabeceras de peticiones.
            self._add_response_listener(monitor)
        else:
            self.logger.warning("Network monitor not available for session capture")

        # Step 1: Login to Rosetta Stone
        await self.login_use_case.execute(credentials)

        # Step 2: Detect the product and navigate into it
        await self.navigate_use_case.execute()
        product = self.navigate_use_case.product

        # Step 3: Wait for the session data the detected product needs
        if product in (RosettaProduct.FLUENCY_BUILDER, RosettaProduct.EXAM):
            label = "Exam / Assessment (gaia)" if product == RosettaProduct.EXAM else "Fluency Builder (gaia)"
            await self._wait_for_capture(
                self.fluency_capturer,
                label,
                require_exam_data=product == RosettaProduct.EXAM,
            )
            captured_data = dict(self.fluency_capturer.get_captured_data())
        else:
            await self._wait_for_capture(self.session_capturer, "Foundations")
            captured_data = dict(self.session_capturer.get_captured_data())

        # Stop network interception
        if monitor:
            monitor.remove_request_listener(self.session_capturer.handle_request)
            monitor.remove_request_listener(self.fluency_capturer.handle_request)
            self._remove_response_listener(monitor)

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
        # Reported by the verification flow: the institutional step is the
        # usual suspect when a login "succeeds" but captures nothing.
        captured_data["institution_selected"] = getattr(
            getattr(self.login_use_case, "login_page", None),
            "institution_selected",
            False,
        )

        # Comprobación: lo que la plataforma dice que esta cuenta ha estudiado.
        # Es lo único que no sale de nuestras propias suposiciones.
        captured_data.update(await self._read_learner_hours())

        self.logger.info(f"Product entry workflow completed ({product.value})")
        return captured_data

    def _add_response_listener(self, monitor: Any) -> None:
        """Escucha respuestas, si el monitor sabe hacerlo."""
        adder = getattr(monitor, "add_response_listener", None)
        if adder is None:
            self.logger.debug(
                "El monitor de red no escucha respuestas; no habrá horas del panel"
            )
            return
        adder(self.learner_auth_capturer.handle_response)

    def _remove_response_listener(self, monitor: Any) -> None:
        remover = getattr(monitor, "remove_response_listener", None)
        if remover is not None:
            remover(self.learner_auth_capturer.handle_response)

    async def _read_learner_hours(self) -> Dict[str, Any]:
        """Horas reconocidas por la plataforma, más las credenciales que las leen.

        Devuelve solo lo que consiguió: sin panel inyectado, sin credenciales o
        con el panel caído, la corrida continúa exactamente igual que antes.
        """
        learner_auth = self.learner_auth_capturer.get_captured_data()
        enriched: Dict[str, Any] = {
            key: value for key, value in learner_auth.items() if value
        }

        if self.learner_dashboard is None:
            return enriched
        if not self.learner_auth_capturer.is_complete():
            self.logger.info(
                "Sin credenciales del panel del aprendiz: no se pueden leer las horas"
            )
            return enriched

        hours = await self.learner_dashboard.get_hours(
            learner_auth["access_token"], learner_auth["user_guid"]
        )
        if hours is None:
            return enriched

        enriched["hours_total"] = hours.total_hours
        enriched["hours_elearning"] = hours.elearning_hours
        self.logger.info(
            "La plataforma reconoce %.3f h totales (%.3f h de curso) a esta cuenta",
            hours.total_hours,
            hours.elearning_hours,
        )
        return enriched

    async def _wait_for_capture(
        self, capturer, label: str, require_exam_data: bool = False
    ) -> None:
        """Poll until ``capturer.is_complete()`` or the timeout elapses."""
        self.logger.info(f"Waiting for {label} session capture to complete...")

        elapsed = 0.0
        while elapsed < self.MAX_CAPTURE_WAIT_SECONDS:
            complete = (
                capturer.is_exam_complete()
                if require_exam_data
                else capturer.is_complete()
            )
            if complete:
                self.logger.info(
                    f"{label} session data captured after {elapsed:.1f}s"
                )
                return

            await asyncio.sleep(self.CAPTURE_POLL_INTERVAL_SECONDS)
            elapsed += self.CAPTURE_POLL_INTERVAL_SECONDS

        if require_exam_data:
            missing = capturer.get_exam_missing_keys()
        elif hasattr(capturer, "get_missing_keys"):
            missing = capturer.get_missing_keys()
        else:
            missing = ["authorization"]
        self.logger.error(
            f"{label} session capture timeout "
            f"({self.MAX_CAPTURE_WAIT_SECONDS}s). Missing data: {missing}"
        )
        raise SessionCaptureIncomplete(missing=missing, product=label)
