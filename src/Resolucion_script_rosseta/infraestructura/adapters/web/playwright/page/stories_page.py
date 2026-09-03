"""La pantalla de Stories: entrar en una historia y salir de en medio.

El listado es una SPA que pinta las fichas bastante después del ``load``, así
que no basta con navegar: hay que esperar a que aparezcan. Las fichas no son
enlaces, son divs, y ``.text-fit-inner`` envuelve exactamente los títulos.

Entrar en la historia es todo lo que se le pide al navegador. Las horas las
reporta ``PlaywrightStoriesApiAdapter`` por la API; esta clase solo consigue
que exista una sesión válida a la que sumárselas.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from Resolucion_script_rosseta.aplicacion.ports.web.control import Selector
from Resolucion_script_rosseta.aplicacion.ports.web.page.stories_page_port import (
    StoriesPagePort,
)
from Resolucion_script_rosseta.aplicacion.ports.web.session import IWebSession

STORIES_URL = "https://totale.rosettastone.com/stories"

TILE_WAIT_SECONDS = 60
TILE_POLL_SECONDS = 2
CONTINUE_LABELS = ("Continuar", "Continue", "Escuchar", "Listen")

# El listado se ha pintado de varias formas: fichas como divs (el caso
# observado), como enlaces, y con marcas data-qa. Se prueban todas antes de
# darlo por perdido: un selector caducado y "esta cuenta no tiene Stories" se
# parecen demasiado desde fuera como para no distinguirlos.
TILE_SELECTORS = (
    ".text-fit-inner",
    "a[href*='/stories/']",
    "[data-qa*='story' i]",
)


class StoriesPage(StoriesPagePort):
    """Adaptador Playwright de la pantalla de Stories."""

    def __init__(self, web_session: IWebSession) -> None:
        super().__init__()
        self.web_session = web_session
        self.TILE_SELECTORS = [Selector.by_css(css) for css in TILE_SELECTORS]

    async def open_stories(self) -> None:
        self.logger.info("Abriendo el listado de historias")
        await self.web_session.navigator.go_to(STORIES_URL, wait_for_load=True)
        await self._click_if_present(("Continuar", "Continue"))

    async def enter_first_story(self) -> Optional[str]:
        tiles = await self._wait_for_tiles()
        if tiles is None:
            await self._report_dead_end()
            return None

        first = tiles.first
        try:
            title = (await first.inner_text()).strip()
        except Exception:  # noqa: BLE001 - el título es informativo, no crítico
            title = ""

        await self.web_session.interactor.click(first)
        self.logger.info("Historia abierta: %s", title or "(sin título)")

        # El reproductor a veces pide un clic más antes de arrancar. Si no está,
        # da igual: lo que importa es que la historia quedó abierta.
        await self._click_if_present(CONTINUE_LABELS)
        return title or "(sin título)"

    async def _wait_for_tiles(self):
        """Espera a que la SPA pinte las fichas. Devuelve el locator o ``None``."""
        deadline = TILE_WAIT_SECONDS
        while deadline > 0:
            for selector in self.TILE_SELECTORS:
                tiles = await self.web_session.interactor.find(selector)
                try:
                    if await tiles.count() > 0:
                        return tiles
                except Exception:  # noqa: BLE001 - la SPA aún está montando el DOM
                    continue
            await asyncio.sleep(TILE_POLL_SECONDS)
            deadline -= TILE_POLL_SECONDS
        return None

    async def _report_dead_end(self) -> None:
        """Deja constancia de *dónde* se quedó, no solo de que no había fichas.

        Sin esto, "la cuenta no tiene Stories", "el selector caducó" y "nos
        rebotaron al login" son el mismo mensaje, y son tres arreglos
        distintos. El título de la página los separa, y la captura remata.
        """
        try:
            title = await self.web_session.navigator.get_title()
        except Exception:  # noqa: BLE001 - el título es un extra, no el objetivo
            title = "(sin título)"

        self.logger.error(
            "El listado de historias no llegó a pintarse. Página: %r. "
            "Puede ser que esta cuenta no tenga Stories en Totale, que la "
            "sesión no llegara autenticada, o que cambiaran las fichas.",
            title,
        )

        dumper = getattr(self.web_session, "debug_dumper", None)
        if dumper is None:
            return
        try:
            await dumper.dump_meta(
                "stories_sin_listado", {"titulo": title, "url": STORIES_URL}
            )
            await dumper.dump_screenshot("stories_sin_listado")
        except Exception as error:  # noqa: BLE001 - diagnosticar no puede fallar más
            self.logger.debug("No se pudo guardar el diagnóstico: %s", error)

    async def _click_if_present(self, labels) -> None:
        """Pulsa el primer rótulo que exista. Nunca tumba la corrida.

        Dos motivos para ``click_first`` y no ``click``: en la portada de
        Stories "Continuar" aparece dos veces — el texto de Dynamic Immersion®
        y el botón — y un locator con dos coincidencias hace saltar el modo
        estricto de Playwright. Y aunque el clic falle, la historia puede estar
        ya abierta: este paso es un empujón, no un requisito.
        """
        for label in labels:
            selector = Selector.by_text(label)
            if not await self.web_session.interactor.exists(selector, timeout=1500):
                continue
            try:
                await self.web_session.interactor.click_first(selector)
                return
            except Exception as error:  # noqa: BLE001 - empujón opcional
                self.logger.debug("No se pudo pulsar %r: %s", label, error)

