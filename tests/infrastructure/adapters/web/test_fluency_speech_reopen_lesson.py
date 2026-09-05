"""Abrir una conversación no puede costar siempre una recarga entera.

``_open_lesson`` hacía ``goto`` + tarjeta de curso + tarjeta de lección + mapa
en **cada** actividad, y las conversaciones van por parejas dentro de la misma
lección (``WithReco`` + ``WithoutReco``): la segunda repetía paso por paso la
navegación que acababa de hacer la primera.

Lo que no puede pasar es fiarse de la nota: si el reproductor ya no está en el
mapa —lo normal al salir de una actividad, y siempre en el reintento del
micrófono— hay que navegar como antes.
"""

import asyncio

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Loc:
    def __init__(self, page, test_id, visible=True):
        self.page = page
        self.test_id = test_id
        self.visible = visible

    @property
    def first(self):
        return self

    def filter(self, has_text=None):
        return self

    async def count(self):
        return 1

    async def is_visible(self):
        return self.visible

    async def wait_for(self, state=None, timeout=None):
        return None

    async def click(self, **kwargs):
        self.page.clics.append(self.test_id)

    def get_by_test_id(self, test_id):
        return _Loc(self.page, test_id)


class _Page:
    def __init__(self, mapa_visible=False):
        self.navegaciones = []
        self.clics = []
        self.mapa_visible = mapa_visible

    async def goto(self, url):
        self.navegaciones.append(url)

    def get_by_test_id(self, test_id):
        visible = self.mapa_visible if test_id == "ActivityMapList" else True
        return _Loc(self, test_id, visible)


def _abrir(page, veces=1, leccion="Registration"):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    for _ in range(veces):
        asyncio.run(speech._open_lesson("B1", leccion))
    return speech


class TestReabrirLeccion:
    def test_la_primera_vez_navega(self):
        page = _Page()
        _abrir(page)
        assert page.navegaciones == ["https://learn.rosettastone.com"]

    def test_la_segunda_actividad_de_la_misma_leccion_no_recarga(self):
        """El caso que se repite: dos conversaciones seguidas en una lección."""
        page = _Page(mapa_visible=True)
        _abrir(page, veces=3)
        assert page.navegaciones == ["https://learn.rosettastone.com"]

    def test_si_el_mapa_ya_no_esta_se_navega_otra_vez(self):
        """Al salir de una actividad el reproductor deja de estar en el mapa."""
        page = _Page(mapa_visible=True)
        speech = _abrir(page)
        page.mapa_visible = False
        asyncio.run(speech._open_lesson("B1", "Registration"))
        assert len(page.navegaciones) == 2

    def test_otra_leccion_siempre_navega(self):
        page = _Page(mapa_visible=True)
        speech = _abrir(page)
        asyncio.run(speech._open_lesson("B1", "At the Airport"))
        assert len(page.navegaciones) == 2
