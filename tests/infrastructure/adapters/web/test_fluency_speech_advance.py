"""Pasar al enunciado siguiente cuando la respuesta ya se aceptó.

De una corrida real: con la respuesta correcta, el pie se vuelve morado con
"Esta es la respuesta correcta" y el botón pasa a "Próximo paso" — pero llega
deshabilitado mientras suena la confirmación. Un único clic, dado nada más
conocerse el veredicto, se perdía, y la espera del enunciado siguiente moría a
los 90 s con el paso ya resuelto en pantalla.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Boton:
    def __init__(self):
        self.clicks = 0

    async def click(self, **kwargs):
        self.clicks += 1


class _Page:
    """El enunciado cambia después de *avanza_tras* clics."""

    def __init__(self, avanza_tras=1, habilita=True):
        self.avanza_tras = avanza_tras
        self.habilita = habilita
        self.boton = _Boton()
        self.consultado = []

    def get_by_test_id(self, test_id):
        return self.boton

    async def wait_for_function(self, expression, *, arg=None, timeout=None):
        self.consultado.append(expression)
        if "SubmitButton" in expression:
            if not self.habilita:
                raise PlaywrightTimeoutError("sigue deshabilitado")
            return None
        # La espera del enunciado.
        if self.boton.clicks < self.avanza_tras:
            raise PlaywrightTimeoutError("el enunciado no ha cambiado")

    async def evaluate(self, expression, *args):
        return None

    async def screenshot(self, path=None):
        return None


def _avanzar(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._advance_to_next_step("el enunciado de antes"))


class TestAdvance:
    def test_one_click_is_usually_enough(self):
        page = _Page(avanza_tras=1)
        assert _avanzar(page) is True
        assert page.boton.clicks == 1

    def test_it_presses_again_when_the_first_click_is_lost(self):
        """El botón llega deshabilitado y se traga la primera pulsación."""
        page = _Page(avanza_tras=2)
        assert _avanzar(page) is True
        assert page.boton.clicks == 2

    def test_it_waits_for_the_button_before_pressing(self):
        page = _Page()
        _avanzar(page)
        assert "SubmitButton" in page.consultado[0]

    def test_a_button_that_never_enables_is_still_pressed(self):
        """El atributo puede no estar: no pulsarlo sería peor."""
        page = _Page(avanza_tras=1, habilita=False)
        assert _avanzar(page) is True
        assert page.boton.clicks == 1

    def test_it_gives_up_instead_of_pressing_forever(self):
        page = _Page(avanza_tras=99)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        assert asyncio.run(speech._advance_to_next_step("antes")) is False
        assert page.boton.clicks == speech.speech_attempts

    def test_the_prompt_is_compared_by_keyword(self):
        """``arg`` es keyword-only en Playwright; por posición es un TypeError."""
        page = _Page()
        _avanzar(page)  # no lanza: el doble copia la firma real
