"""Scope resolution utilities for Playwright interactions."""

from typing import Optional, Union
from playwright.async_api import FrameLocator, Locator, Page

Scope = Union[Page, Locator, FrameLocator]


class ScopeResolver:
    """Handles scope resolution for Playwright interactions."""

    def __init__(self, page: Page):
        self._page = page
        self._ambient_frame: Optional[FrameLocator] = None

    @property
    def ambient_frame(self) -> Optional[FrameLocator]:
        """Get the current ambient frame."""
        return self._ambient_frame

    @ambient_frame.setter
    def ambient_frame(self, frame: Optional[FrameLocator]) -> None:
        """Set the current ambient frame."""
        self._ambient_frame = frame

    def resolve_scope(
        self,
        within: Optional[Scope],
        within_frame: Optional[str],
    ) -> Scope:
        """
        Resolve the scope for a Playwright interaction.

        Scope precedence:
        1) explicit `within` (Locator/FrameLocator/Page)
        2) ambient frame (set by within_frame context manager)
        3) explicit `within_frame` css/xpath
        4) page

        Args:
            within: Explicit scope (Page, Locator, or FrameLocator)
            within_frame: CSS/XPath selector for iframe

        Returns:
            Resolved scope for the interaction
        """
        if within is not None:
            return within
        if self._ambient_frame is not None:
            return self._ambient_frame
        if within_frame:
            return self._page.frame_locator(within_frame)
        return self._page
