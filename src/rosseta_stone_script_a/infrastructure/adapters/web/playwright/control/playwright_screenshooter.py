from typing import Optional

from playwright.async_api import Page

from rosseta_stone_script_a.application.ports.web import ScreenShootterPort
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin


class ScreenshotterAdapter(ScreenShootterPort, LoggingMixin):
    """Adapter that implements web interaction methods using Playwright."""

    def __init__(self, page: Page):
        super().__init__()
        self._page = page

    async def take_screenshot(self, path: Optional[str] = None) -> bytes:
        """Take a screenshot of the current page.

        Args:
            path (Optional[str]): Optional file path to save the screenshot.

        Returns:
            bytes: The screenshot image in bytes.
        """
        self.logger.info(f"Taking screenshot. Saving to: {path if path else 'memory'}")
        screenshot_bytes = await self._page.screenshot(path=path)
        return screenshot_bytes
