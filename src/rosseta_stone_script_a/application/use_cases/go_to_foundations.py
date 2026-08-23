from rosseta_stone_script_a.application.ports.web import IWebSession
from rosseta_stone_script_a.application.ports.web.page import DashboardPagePort
from rosseta_stone_script_a.domain.values.rosetta_product import RosettaProduct

from ..ports.use_case import UseCasePort


class GoToFundationsUseCase(UseCasePort):
    """
    Use case for navigating into the account's product from the dashboard.

    Detects whether the account offers Foundations or Fluency Builder and opens
    the matching workspace, exposing the detected product via ``self.product``.
    """

    def __init__(
        self,
        web_session: IWebSession,
        dashboard_page: DashboardPagePort,
    ):
        self.web_session = web_session
        self.dashboard_page = dashboard_page
        self.user_name: str | None = None
        self.product: RosettaProduct = RosettaProduct.UNKNOWN

    async def execute(self) -> None:
        """Detect the product and navigate into it from the dashboard."""
        self.logger.info("Navigating into product from dashboard")

        # Capture user name from dashboard
        await self._capture_user_name()

        self.product = await self.dashboard_page.detect_product()

        if self.product == RosettaProduct.FOUNDATIONS:
            await self.dashboard_page.open_foundations()
            screenshot = "foundations_workspace"
        elif self.product == RosettaProduct.FLUENCY_BUILDER:
            await self.dashboard_page.open_fluency_builder()
            screenshot = "fluency_builder_workspace"
        elif self.product == RosettaProduct.EXAM:
            await self.dashboard_page.open_exam()
            screenshot = "exam_workspace"
        else:
            raise RuntimeError(
                "Dashboard offers no known product (neither Foundations nor "
                "Fluency Builder). Cannot continue."
            )

        # Wait for page to load
        await self.web_session.navigator.wait_for_load()

        self.logger.info(f"Successfully navigated into {self.product.value}")
        await self.web_session.debug_dumpper.dump_screenshot(screenshot)

    async def _capture_user_name(self) -> None:
        """Capture the user name from the dashboard."""
        try:
            self.user_name = await self.dashboard_page.get_user_name()
            if self.user_name:
                self.logger.info(f"Captured user name: {self.user_name}")
            else:
                self.logger.warning("Could not capture user name from dashboard")
        except Exception as e:
            self.logger.error(f"Error capturing user name: {e}")
