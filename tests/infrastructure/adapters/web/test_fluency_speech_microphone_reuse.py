"""El reproductor pide el micrófono una vez y lo reutiliza.

Con la comprobación de micrófono ya superada, el paso siguiente esperaba a que
``getUserMedia`` se llamara otra vez al pulsar el botón de voz. No se llama:
el reproductor se queda con el ``MediaStream`` que abrió la comprobación. La
espera moría a los 90 s con "que el reproductor pida el micrófono", que además
señalaba al sitio equivocado — el micrófono estaba conectado desde el principio.
"""

import asyncio

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page import (
    fluency_speech_page as modulo,
)
from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Page:
    """Copia la firma real de Playwright: ``arg`` es **keyword-only**.

    Pasarlo por posición es un ``TypeError`` que aquí salía disfrazado de
    "Speech browser flow failed" a mitad de la actividad, no al arrancar. Un
    doble permisivo (``*args``) se lo tragaba y los tests seguían en verde.
    """

    def __init__(self, peticion_nueva=False, conectado=True):
        self.peticion_nueva = peticion_nueva
        self.conectado = conectado
        self.esperas = []

    async def wait_for_function(self, expression, *, arg=None, timeout=None):
        self.esperas.append((expression, arg))
        if not self.peticion_nueva:
            raise PlaywrightTimeoutError("agotado")

    async def evaluate(self, expression, *args):
        return self.conectado

    async def screenshot(self, path=None):
        return None


def _esperar(page, antes=0):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    asyncio.run(speech._wait_for_microphone(antes))


class TestMicrophoneReuse:
    def test_a_fresh_request_is_enough(self):
        page = _Page(peticion_nueva=True)
        _esperar(page, antes=2)
        expresion, argumento = page.esperas[0]
        assert "__rosettaMicRequests" in expresion
        assert argumento == 2  # y va por keyword, no por posición


class TestWaitHelper:
    def test_the_shared_wait_passes_its_argument_by_keyword(self):
        """La misma trampa estaba en ``_wait``, sin haberse ejecutado nunca.

        Solo la usa la espera de "que el reproductor pase al siguiente paso",
        a la que ninguna corrida había llegado.
        """
        page = _Page(peticion_nueva=True)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._wait("() => true", "una espera con argumento", "hola"))
        assert page.esperas[0][1] == "hola"

    def test_reusing_the_check_microphone_is_not_a_failure(self):
        """Lo normal: no hay petición nueva, pero el micrófono está puesto."""
        page = _Page(peticion_nueva=False, conectado=True)
        _esperar(page)  # no lanza

    def test_it_only_waits_the_short_probe(self):
        """No son 90 s: si no hay petición nueva, casi nunca la habrá."""
        page = _Page(peticion_nueva=True)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._wait_for_microphone(0))
        assert speech.probe_timeout_ms < speech.timeout_ms

    def test_no_microphone_at_all_is_still_an_error(self):
        page = _Page(peticion_nueva=False, conectado=False)
        with pytest.raises(RuntimeError):
            _esperar(page)


class TestRequestCounter:
    def test_the_script_counts_the_requests(self):
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "__rosettaMicRequests" in guion

    def test_the_step_does_not_clear_the_ready_flag(self):
        """Ponerlo a false y esperar a que vuelva era esperar a nada."""
        import inspect

        fuente = inspect.getsource(PlaywrightFluencySpeechPage._complete_visible_step)
        assert "__rosettaMicReady = false" not in fuente

