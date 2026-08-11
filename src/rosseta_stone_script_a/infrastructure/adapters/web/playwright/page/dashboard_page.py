from __future__ import annotations

import re
from typing import Optional

from rosseta_stone_script_a.application.ports.web.control import Selector
from rosseta_stone_script_a.application.ports.web.page import DashboardPagePort
from rosseta_stone_script_a.application.ports.web.session import IWebSession
from rosseta_stone_script_a.domain.values.rosetta_product import RosettaProduct
from rosseta_stone_script_a.infrastructure.adapters.web.playwright.patterns import (
    LessonPatterns,
)


class DashboardPage(DashboardPagePort):
    """
    Dashboard page adapter for navigating to Foundations.
    All interactions go through self.web_session.interactor.
    """

    def __init__(self, web_session: IWebSession) -> None:
        super().__init__()
        self.web_session = web_session

        # Selectors for Foundations navigation
        self.FOUNDATIONS_BTN = Selector.by_text(LessonPatterns.FOUNDATIONS)
        self.FLUENCY_BUILDER_BTN = Selector.by_text(LessonPatterns.FLUENCY_BUILDER)
        # Selector for user name on dashboard
        self.USER_NAME_SELECTOR = Selector.by_css('[data-qa="DashboardUserName"]')

    async def detect_product(self) -> RosettaProduct:
        """Detect which product this account offers, without navigating or failing.

        Checks for the Foundations entry point first, then Fluency Builder. Returns
        UNKNOWN if neither is present (e.g. an unexpected dashboard layout).
        """
        self.logger.info("Detecting product on dashboard")
        if await self.web_session.interactor.exists(self.FOUNDATIONS_BTN, timeout=2000):
            self.logger.info("Detected product: Foundations")
            return RosettaProduct.FOUNDATIONS
        if await self.web_session.interactor.exists(
            self.FLUENCY_BUILDER_BTN, timeout=2000
        ):
            self.logger.info("Detected product: Fluency Builder")
            return RosettaProduct.FLUENCY_BUILDER
        self.logger.warning("No known product entry point found on dashboard")
        return RosettaProduct.UNKNOWN

    async def open_foundations(self) -> None:
        """Navigate to Foundations from the dashboard."""
        self.logger.info("Attempting to open Foundations from dashboard")
        product = await self.detect_product()
        try:
            if product == RosettaProduct.FOUNDATIONS:
                self.logger.info("Found Foundations button, clicking it")
                await self.web_session.interactor.click(self.FOUNDATIONS_BTN)
            elif product == RosettaProduct.FLUENCY_BUILDER:
                # The dashboard loaded fine — this account simply subscribes to a
                # product this navigation does not target. Say so, so the failure is
                # not mistaken for a stale selector.
                self.logger.error("Dashboard offers Fluency Builder, not Foundations")
                raise RuntimeError(
                    "This account uses Fluency Builder, not Foundations."
                )
            else:
                self.logger.error("Foundations navigation element not found")
                raise RuntimeError("Foundations navigation element not found")
            self.logger.info("Successfully opened Foundations")
        except Exception as e:
            self.logger.error(f"Failed to navigate to Foundations: {e}")
            raise RuntimeError(f"Failed to navigate to Foundations: {e}")

    async def open_fluency_builder(self) -> None:
        """Navigate into Fluency Builder by clicking its product tile."""
        self.logger.info("Attempting to open Fluency Builder from dashboard")
        try:
            if not await self.web_session.interactor.exists(
                self.FLUENCY_BUILDER_BTN, timeout=2000
            ):
                raise RuntimeError("Fluency Builder navigation element not found")
            await self.web_session.interactor.click(self.FLUENCY_BUILDER_BTN)
            self.logger.info("Successfully opened Fluency Builder")
        except Exception as e:
            self.logger.error(f"Failed to navigate to Fluency Builder: {e}")
            raise RuntimeError(f"Failed to navigate to Fluency Builder: {e}")

    async def get_user_name(self) -> Optional[str]:
        """Get the user's name displayed on the dashboard."""
        self.logger.info("Attempting to get user name from dashboard")
        try:
            text = await self.web_session.interactor.get_text(
                self.USER_NAME_SELECTOR, timeout=5000
            )
            if text:
                # Extract just the name from "Hello, Name!" format
                # The text content is like: "Hello, Briggitte Naomy Casquete Valenzuela!"
                match = re.search(r"Hello,\s*(.+?)!", text)
                if match:
                    name = match.group(1).strip()
                    self.logger.info(f"Found user name: {name}")
                    return name
                # If no match, return the raw text without "Hello, " prefix
                name = text.replace("Hello,", "").strip().rstrip("!")
                self.logger.info(f"Extracted user name: {name}")
                return name
            self.logger.warning("User name element found but text is empty")
            return None
        except Exception as e:
            self.logger.error(f"Failed to get user name: {e}")
            return None
