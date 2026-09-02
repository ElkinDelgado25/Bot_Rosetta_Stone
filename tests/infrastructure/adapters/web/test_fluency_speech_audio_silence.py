"""Esperar el silencio no puede depender de que suene un solo altavoz.

Medido en una corrida real (02-09-2026): en un paso pueden estar sonando **dos**
``audio_playing`` a la vez — el del enunciado y el de la respuesta recién
pulsada. Se esperaba con un locator, que con dos coincidencias hace saltar el
modo estricto de Playwright; y como ocurre a mitad de la conversación, se
llevaba por delante la actividad entera con un "Speech browser flow failed" que
no menciona el audio por ninguna parte.

``count()`` no avisa del choque: devuelve 2, el ``if`` pasa, y revienta el
``wait_for``. Es la misma trampa que ya está documentada para Stories.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _LocatorEstricto:
    """Como Playwright: con más de una coincidencia, esperar es un error."""

    def __init__(self, coincidencias):
        self.coincidencias = coincidencias

    async def count(self):
        return self.coincidencias

    async def wait_for(self, state=None, timeout=None):
        if self.coincidencias > 1:
            raise AssertionError(
                "strict mode violation: resolved to %d elements" % self.coincidencias
            )


class _Page:
    def __init__(self, coincidencias=2, se_calla=True):
        self.coincidencias = coincidencias
        self.se_calla = se_calla
        self.expresiones = []

    def locator(self, selector):
        return _LocatorEstricto(self.coincidencias)

    async def wait_for_function(self, expression, timeout=None, arg=None):
        self.expresiones.append(expression)
        if not self.se_calla:
            raise PlaywrightTimeoutError("sigue sonando")


def _esperar(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._wait_for_all_audio_to_stop())


class TestEsperarSilencio:
    def test_two_speakers_playing_is_not_an_error(self):
        """El caso que tumbaba la conversación: dos altavoces a la vez."""
        page = _Page(coincidencias=2)
        _esperar(page)
        assert page.expresiones, "no se esperó por la condición en JS"

    def test_it_waits_for_all_of_them_not_just_the_first(self):
        """Queremos silencio, no que se vaya el primero de los dos."""
        page = _Page(coincidencias=2)
        _esperar(page)
        assert "!document.querySelector('[data-qa=audio_playing]')" in (
            page.expresiones[0]
        )

    def test_audio_that_never_stops_does_not_sink_the_activity(self):
        page = _Page(coincidencias=1, se_calla=False)
        _esperar(page)  # no debe propagar
