"""Frame context management utilities."""

from contextlib import asynccontextmanager
from typing import Optional
from playwright.async_api import Page
from rosseta_stone_script_a.application.ports.web import Selector
from .scope_resolver import ScopeResolver


class FrameManager:
    """Manages frame context for Playwright interactions."""

    def __init__(self, page: Page, scope_resolver: ScopeResolver):
        self._page = page
        self._scope_resolver = scope_resolver

    @asynccontextmanager
    async def within_frame(self, frame_selector: Optional[Selector] = None):
        """
        Context manager for interactions within a specific frame.

        Usage:
            async with frame_manager.within_frame(Selector(kind=..., value='iframe#app')):
                # All interactions here will target that frame

        Notes:
          - Expects `frame_selector.value` to be a CSS/XPath string understood by Playwright's frame_locator.
          - All actions inside the context will target that frame unless overridden by `within=` or `within_frame=`.

        Args:
            frame_selector: Selector for the target frame

        Raises:
            TypeError: If frame_selector.value is not a string
        """
        prev_frame = self._scope_resolver.ambient_frame
        try:
            if frame_selector is None:
                self._scope_resolver.ambient_frame = None
            else:
                query = frame_selector.value  # string selector for frame_locator
                if not isinstance(query, str):
                    raise TypeError(
                        "frame_selector.value must be a CSS/XPath string for frame_locator"
                    )
                self._scope_resolver.ambient_frame = self._page.frame_locator(query)
            yield
        finally:
            self._scope_resolver.ambient_frame = prev_frame
