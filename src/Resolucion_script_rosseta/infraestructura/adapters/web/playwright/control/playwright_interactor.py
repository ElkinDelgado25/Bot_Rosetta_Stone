from __future__ import annotations

from typing import Optional, Union

from playwright.async_api import Locator, Page

from Resolucion_script_rosseta.aplicacion.ports.web import InteractorPort, Selector
from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin
from .utils.frame_manager import FrameManager
from .utils.scope_resolver import Scope, ScopeResolver
from .utils.selector_converter import SelectorConverter

_SECRET_HINTS = ("contrase", "password", "passwd", "[type=password]")


def _mask_if_secret(loc: Locator, text: str) -> str:
    """Return *text*, or a masked stand-in when *loc* looks like a secret field.

    The fill log prints the value being typed, which would otherwise write the
    account password to the logs in plaintext.
    """
    haystack = repr(loc).lower()
    if any(hint in haystack for hint in _SECRET_HINTS):
        return "*" * 8
    return text


class InteractorAdapter(InteractorPort, LoggingMixin):
    """Adapter that implements web interaction methods using Playwright."""

    def __init__(self, page: Page):
        super().__init__()
        self._page = page

        # Initialize utility components
        self._scope_resolver = ScopeResolver(page)
        self._selector_converter = SelectorConverter()
        self._frame_manager = FrameManager(page, self._scope_resolver)

    # ---------- Factory principal: convierte Selector -> Locator ----------
    async def find(
        self,
        selector: Selector,
        *,
        within: Optional[Scope] = None,
        within_frame: Optional[str] = None,  # opcional: CSS/xpath para iframes
    ) -> Locator:
        """
        Devuelve un Locator según el Selector de la capa Application.
        - within: limitar la búsqueda a un contenedor (Locator) o FrameLocator.
        - within_frame: si lo pasas, se usa frame_locator(within_frame) como scope.
        - ambient frame: si estás dentro de `async with within_frame(...):`, se usa por defecto.
        """
        scope: Scope = self._scope_resolver.resolve_scope(within, within_frame)
        return self._selector_converter.convert_to_locator(selector, scope)

    # ---------- Helpers internos ----------
    async def _ensure_locator(
        self,
        target: Union[Selector, Locator],
        **kwargs,
    ) -> Locator:
        if isinstance(target, Locator):
            return target
        # target es un Selector de la capa Application
        return await self.find(target, **kwargs)

    def within_frame(self, frame_selector: Optional[Selector] = None):
        """
        Context manager for interactions within a specific frame.
        Delegates to the FrameManager for frame context handling.
        """
        return self._frame_manager.within_frame(frame_selector)

    # ---------- Acciones de alto nivel ----------
    async def click(
        self,
        target: Union[Selector, Locator],
        *,
        within: Optional[Scope] = None,
        within_frame: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Click robusto sobre un Locator resuelto por Selector o Locator directo.
        Puedes pasar kwargs propios de Playwright (force, trial, timeout, etc.)
        """
        loc = await self._ensure_locator(
            target, within=within, within_frame=within_frame
        )
        self.logger.info(f"Click -> {loc}")
        await loc.click(**kwargs)

    async def click_first(
        self,
        target: Union[Selector, Locator],
        *,
        within: Optional[Scope] = None,
        within_frame: Optional[str] = None,
        **kwargs,
    ):
        loc = await self._ensure_locator(
            target, within=within, within_frame=within_frame
        )
        await loc.first.click(**kwargs)

    async def exists(
        self,
        target: Union[Selector, Locator],
        timeout: int = 0,
        *,
        within: Optional[Scope] = None,
        within_frame: Optional[str] = None,
    ) -> bool:
        try:
            loc = await self._ensure_locator(
                target, within=within, within_frame=within_frame
            )
            await loc.first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    async def fill(
        self,
        target: Union[Selector, Locator],
        text: str,
        *,
        within: Optional[Scope] = None,
        within_frame: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Rellena inputs/textarea de forma estable usando Locator.
        """
        loc = await self._ensure_locator(
            target, within=within, within_frame=within_frame
        )
        self.logger.info(f"Fill -> {loc} text='{_mask_if_secret(loc, text)}'")
        await loc.fill(text, **kwargs)

    async def press(
        self,
        key: str,
        target: Optional[Union[Selector, Locator]] = None,
        *,
        within: Optional[Scope] = None,
        within_frame: Optional[str] = None,
        **kwargs,
    ) -> None:
        """
        Presiona una tecla. Si no pasas target, usa el keyboard de la Page.
        """
        if target is None:
            self.logger.info(f"Press (page) -> {key}")
            await self._page.keyboard.press(key)
            return

        loc = await self._ensure_locator(
            target, within=within, within_frame=within_frame
        )
        self.logger.info(f"Press -> {loc} key='{key}'")
        await loc.press(key, **kwargs)

    async def get_text(
        self,
        target: Union[Selector, Locator],
        timeout: int = 5000,
        *,
        within: Optional[Scope] = None,
        within_frame: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get the text content of an element.
        Returns None if the element is not found.
        """
        try:
            loc = await self._ensure_locator(
                target, within=within, within_frame=within_frame
            )
            await loc.first.wait_for(state="visible", timeout=timeout)
            text = await loc.first.text_content()
            self.logger.info(f"GetText -> {loc} text='{text}'")
            return text
        except Exception as e:
            self.logger.warning(f"Failed to get text from element: {e}")
            return None

