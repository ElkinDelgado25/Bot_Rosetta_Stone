"""Selector to Locator conversion utilities."""

import re
from typing import Pattern, Union
from playwright.async_api import Locator
from Resolucion_script_rosseta.aplicacion.ports.web import Selector, SelectorKind
from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin
from .regex_utils import compile_slash_regex
from .scope_resolver import Scope


class SelectorConverter(LoggingMixin):
    """Converts application layer Selectors to Playwright Locators."""

    def __init__(self):
        super().__init__()

    def convert_to_locator(
        self,
        selector: Selector,
        scope: Scope,
    ) -> Locator:
        """
        Convert a Selector to a Playwright Locator within the given scope.

        Args:
            selector: Application layer selector
            scope: Playwright scope (Page, Locator, or FrameLocator)

        Returns:
            Playwright Locator

        Raises:
            NotImplementedError: If the selector kind is not supported
        """
        kind = selector.kind

        if kind == SelectorKind.ROLE:
            return self._convert_role_selector(selector, scope)

        if kind == SelectorKind.TEST_ID:
            self.logger.info(f"[convert] TEST_ID value={selector.value!r}")
            return scope.get_by_test_id(selector.value)

        if kind == SelectorKind.LABEL:
            self.logger.info(f"[convert] LABEL value={selector.value!r}")
            return scope.get_by_label(selector.value)

        if kind == SelectorKind.PLACEHOLDER:
            self.logger.info(f"[convert] PLACEHOLDER value={selector.value!r}")
            return scope.get_by_placeholder(selector.value)

        if kind == SelectorKind.TEXT:
            return self._convert_text_selector(selector, scope)

        if kind == SelectorKind.CSS:
            self.logger.info(f"[convert] CSS value={selector.value!r}")
            return scope.locator(selector.value)

        # Future: CSS passthrough could be added here
        raise NotImplementedError(f"SelectorKind not supported: {kind}")

    def _convert_role_selector(self, selector: Selector, scope: Scope) -> Locator:
        """Convert a role-based selector to a Locator."""
        role = selector.role or "button"
        name = selector.name or selector.value

        # name can be str, regex-like "/.../i", or re.Pattern
        name_arg: Union[str, Pattern, None] = None
        if isinstance(name, re.Pattern):
            name_arg = name
        elif isinstance(name, str):
            name_arg = compile_slash_regex(name) or name

        self.logger.info(f"[convert] ROLE role={role} name={name!r}")
        return scope.get_by_role(role, name=name_arg)

    def _convert_text_selector(self, selector: Selector, scope: Scope) -> Locator:
        """Convert a text-based selector to a Locator."""
        self.logger.info(f"[convert] TEXT value={selector.value!r}")
        val = selector.value

        if isinstance(val, re.Pattern):
            return scope.get_by_text(val)
        if isinstance(val, str):
            rx = compile_slash_regex(val)
            return scope.get_by_text(rx if rx else val)

        return scope.get_by_text(val)

