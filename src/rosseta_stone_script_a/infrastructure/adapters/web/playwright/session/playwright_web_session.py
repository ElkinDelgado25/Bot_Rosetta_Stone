from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page
from playwright._impl._errors import TargetClosedError

from rosseta_stone_script_a.application.ports.web import (
    DebugDumperPort,
    InteractorPort,
    IWebSession,
    NavigatorPort,
    NetworkMonitorPort,
    ScreenShootterPort,
)
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin

from ..common import Viewport
from ..control import (
    InteractorAdapter,
    NavigatorAdapter,
    PlaywrightNetworkMonitor,
    ScreenshotterAdapter,
)
from ..diagnostics.playwright_debug_dumper import PlaywrightFileDebugDumperAdapter


class PlaywrightWebSession(IWebSession, LoggingMixin):
    """Adapter that implements web interaction methods using Playwright."""

    def __init__(
        self,
        browser: Browser,
        user_agent: str = None,
        locale: str = None,
        viewport: Viewport = None,
    ):
        super().__init__()
        self._browser = browser
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self.user_agent = user_agent
        self.locale = locale
        self.viewport = viewport

        self.navigator: NavigatorPort | None = None
        self.interactor: InteractorPort | None = None
        self.network_monitor: NetworkMonitorPort | None = None
        self.screenshotter: ScreenShootterPort | None = None
        self.screenshotter: ScreenShootterPort | None = None

        self.debug_dumpper: DebugDumperPort | None = None

    @asynccontextmanager
    async def session(self) -> AsyncIterator["PlaywrightWebSession"]:
        """Context manager that creates and cleans up browser context and page."""
        await self._create_context()
        await self._create_page()
        await self._initial_setup()

        try:
            yield self
        finally:
            await self.close()

    async def close(self) -> None:
        """Close web session safely, handling already-closed resources."""
        self.logger.info("Closing web session...")

        # Close page first, ignoring if already closed
        if self._page:
            try:
                await self._page.close()
            except TargetClosedError:
                self.logger.debug("Page was already closed")
            except Exception as e:
                self.logger.warning(f"Error closing page: {e}")

        # Close context, ignoring if already closed
        if self._context:
            try:
                await self._context.close()
            except TargetClosedError:
                self.logger.debug("Context was already closed")
            except Exception as e:
                self.logger.warning(f"Error closing context: {e}")

    async def _create_context(self) -> None:
        """Create browser context with realistic settings."""
        self.logger.info("Creating browser context...")
        if not self._browser:
            self.logger.error("Browser not launched")
            raise RuntimeError("Browser not launched")

        self._context = await self._browser.new_context(
            permissions=[],
            accept_downloads=True,
            user_agent=self.user_agent,
            locale=self.locale,
            viewport=self.viewport,
        )

    async def _create_page(self) -> None:
        """Create the main page."""
        self.logger.info("Creating new page...")
        if not self._context:
            self.logger.error("Browser context not created")
            raise RuntimeError("Browser context not created")

        self._page = await self._context.new_page()

    async def _initial_setup(self) -> None:
        """Perform any initial setup required for the session."""
        self.logger.info("Performing initial setup...")
        self.navigator = NavigatorAdapter(self._page)
        self.interactor = InteractorAdapter(self._page)
        self.network_monitor = PlaywrightNetworkMonitor(self._page)
        self.screenshotter = ScreenshotterAdapter(self._page)
        self.debug_dumpper = PlaywrightFileDebugDumperAdapter(self.screenshotter)
