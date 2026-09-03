"""Cómo se contesta la conversación: hablando o pulsando.

Las dos conversaciones del árbol comparten reproductor y se distinguen por el
``inputType`` de sus pasos: ``speaking`` pinta el micrófono, ``select`` solo las
respuestas. La ruta de navegador exigía el micrófono y se rendía sin él, y de
ahí salió la conclusión de que ``DialogueExpressionWithoutReco`` era imposible:
lo que no servía era la espera, no la actividad.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Locator:
    def __init__(self, cuantos):
        self.cuantos = cuantos

    async def count(self):
        return self.cuantos


class _Page:
    def __init__(self, *, microfonos=0, respuestas=0, pinta_algo=True):
        self.microfonos = microfonos
        self.respuestas = respuestas
        self.pinta_algo = pinta_algo
        self.esperas = []

    async def wait_for_function(self, expression, timeout=None, arg=None):
        self.esperas.append(timeout)
        if not self.pinta_algo:
            raise PlaywrightTimeoutError("no aparece nada")

    def get_by_test_id(self, test_id):
        return _Locator(
            self.microfonos if test_id == "SpeechButton" else self.respuestas
        )


def _modo(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._input_mode())


class TestInputMode:
    def test_a_microphone_means_speaking(self):
        assert _modo(_Page(microfonos=1, respuestas=3)) == "hablar"

    def test_only_choices_means_selecting(self):
        """Es el caso de ``WithoutReco``: hay qué contestar, pero no con la voz."""
        assert _modo(_Page(microfonos=0, respuestas=3)) == "elegir"

    def test_neither_one_is_not_an_activity_we_can_answer(self):
        assert _modo(_Page(pinta_algo=False)) == "desconocido"

    def test_finding_out_uses_the_short_timeout(self):
        """Averiguarlo es una sonda: no puede costar lo que esperar de verdad."""
        page = _Page(pinta_algo=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._input_mode())
        assert page.esperas == [speech.probe_timeout_ms]

