from playwright.async_api import Page

from rosseta_stone_script_a.application.ports.web import NavigatorPort
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin


class NavigatorAdapter(NavigatorPort, LoggingMixin):
    """Adapter that implements web interaction methods using Playwright."""

    def __init__(self, page: Page):
        super().__init__()
        self._page = page

    async def go_to(self, url: str, wait_for_load: bool = True) -> None:
        """Navigate to the specified URL."""
        self.logger.info(f"Navigating to URL: {url}")
        await self._page.goto(url)
        if wait_for_load:
            await self.wait_for_load()

    async def get_title(self) -> str:
        """Get the title of the current page."""
        title = await self._page.title()
        self.logger.info(f"Current page title: {title}")
        return title

    async def wait_for_load(self, timeout: int = 30000) -> None:
        """Wait for the page to fully load."""
        self.logger.info("Waiting for page to load...")
        await self._page.wait_for_load_state("networkidle", timeout=timeout)
