"""Pasar al enunciado siguiente cuando el paso ya está resuelto.

Hacen falta **dos** pulsaciones, y no por lo que se creía. Medido en las trazas
de Playwright (02-09-2026): la primera envía la respuesta y solo cambia el texto
del botón; la segunda es la que avanza el enunciado, y lo hace al instante.

    97.21s  0.02s      Frame.click  SubmitButton          <- clic 1
    97.75s 15.02s ERR  waitForFunction oldPrompt...       <- 15 s en blanco
   112.77s  0.00s      waitForFunction SubmitButton enabled  (ya estaba)
   112.78s  0.05s      Frame.click  SubmitButton          <- clic 2
   113.35s  0.00s      waitForFunction oldPrompt...       <- cambia ya

La explicación anterior —"el botón llega deshabilitado y se traga el primer
clic"— era falsa: la comprobación de habilitado tarda 0,00 s antes del segundo.
Esperar solo al enunciado costaba 15 s por paso en las dos rutas.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)

ANTES = "el enunciado de antes"


class _Boton:
    def __init__(self):
        self.clicks = 0

    @property
    def first(self):
        """Un locator de verdad siempre lo ofrece; el código lo usa."""
        return self

    async def click(self, **kwargs):
        self.clicks += 1


class _Page:
    """Un reproductor de mentira que cambia el botón antes que el enunciado.

    ``avanza_tras`` es cuántos clics hacen falta para que cambie el enunciado.
    ``mueve_boton`` dice si el clic que aún no avanza cambia al menos el texto
    del botón — que es la señal con la que dejamos de esperar a ciegas.
    """

    def __init__(self, avanza_tras=2, habilita=True, mueve_boton=True):
        self.avanza_tras = avanza_tras
        self.habilita = habilita
        self.mueve_boton = mueve_boton
        self.boton = _Boton()
        self.consultado = []
        self.esperas = []

    def get_by_test_id(self, test_id):
        return self.boton

    # -- lo que ve la página -------------------------------------------------
    def _prompt(self):
        return None if self.boton.clicks >= self.avanza_tras else ANTES

    def _texto_boton(self):
        if not self.mueve_boton:
            return "Enviar"
        return "Enviar" if self.boton.clicks == 0 else "Próximo paso"

    async def evaluate(self, expression, *args):
        self.consultado.append(expression)
        return {
            "prompt": self._prompt(),
            "boton": self._texto_boton(),
            "listo": self.habilita,
        }

    async def wait_for_function(self, expression, *, arg=None, timeout=None):
        self.consultado.append(expression)
        self.esperas.append(timeout)
        if "hasAttribute('disabled')" in expression and "prompt" not in expression:
            if not self.habilita:
                raise PlaywrightTimeoutError("sigue deshabilitado")
            return None
        if "datos.prompt" in expression:  # ¿se movió algo?
            movio = self._prompt() != arg["prompt"] or self._texto_boton() != arg["boton"]
            if not movio:
                raise PlaywrightTimeoutError("no se movió nada")
            return None
        # La espera larga del enunciado, que ya solo se usa de último recurso.
        if self._prompt() is not None:
            raise PlaywrightTimeoutError("el enunciado no ha cambiado")

    async def screenshot(self, path=None):
        return None


def _avanzar(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._advance_to_next_step(ANTES))


class TestAdvance:
    def test_two_clicks_are_what_a_step_costs(self):
        page = _Page(avanza_tras=2)
        assert _avanzar(page) is True
        assert page.boton.clicks == 2

    def test_one_click_is_enough_when_the_player_advances_at_once(self):
        page = _Page(avanza_tras=1)
        assert _avanzar(page) is True
        assert page.boton.clicks == 1

    def test_it_does_not_wait_the_long_probe_between_clicks(self):
        """Lo que sobraba: 15 s por paso esperando un enunciado que no cambia.

        Mirando también el botón, entre clic y clic se espera la sonda corta.
        """
        page = _Page(avanza_tras=2)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._advance_to_next_step(ANTES))
        assert speech._ADVANCE_PROBE_MS < speech.probe_timeout_ms
        assert speech.probe_timeout_ms not in page.esperas

    def test_an_already_advanced_step_is_never_clicked(self):
        """La guarda que impide saltarse un paso.

        Si el enunciado ya cambió, otro clic caería sobre el "Omitir" del paso
        siguiente y lo dejaría sin contestar.
        """
        page = _Page(avanza_tras=0)
        assert _avanzar(page) is True
        assert page.boton.clicks == 0

    def test_a_button_that_never_enables_is_still_pressed(self):
        """El atributo puede no estar: no pulsarlo sería peor."""
        page = _Page(avanza_tras=1, habilita=False)
        assert _avanzar(page) is True
        assert page.boton.clicks == 1

    def test_a_player_that_shows_no_sign_still_gets_the_long_wait(self):
        """Sin señal ninguna se conserva la espera de antes, como último recurso."""
        page = _Page(avanza_tras=99, mueve_boton=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        assert asyncio.run(speech._advance_to_next_step(ANTES)) is False
        assert speech.probe_timeout_ms in page.esperas

    def test_it_gives_up_instead_of_pressing_forever(self):
        page = _Page(avanza_tras=99)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        assert asyncio.run(speech._advance_to_next_step(ANTES)) is False
        assert page.boton.clicks == speech.speech_attempts

