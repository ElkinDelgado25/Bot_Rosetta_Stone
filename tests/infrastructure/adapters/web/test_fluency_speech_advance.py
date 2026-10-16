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

import pytest
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

    async def count(self):
        return 0

    async def is_visible(self):
        return False


class _Page:
    """Un reproductor de mentira que cambia el botón antes que el enunciado.

    ``avanza_tras`` es cuántos clics hacen falta para que cambie el enunciado.
    ``mueve_boton`` dice si el clic que aún no avanza cambia al menos el texto
    del botón — que es la señal con la que dejamos de esperar a ciegas.
    """

    def __init__(self, avanza_tras=2, habilita=True, mueve_boton=True, etiqueta=None):
        self.avanza_tras = avanza_tras
        self.habilita = habilita
        self.mueve_boton = mueve_boton
        self.etiqueta = etiqueta
        self.boton = _Boton()
        self.consultado = []
        self.esperas = []

    def get_by_test_id(self, test_id):
        return self.boton

    # -- lo que ve la página -------------------------------------------------
    def _prompt(self):
        return None if self.boton.clicks >= self.avanza_tras else ANTES

    def _texto_boton(self):
        if self.etiqueta:
            return self.etiqueta
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

    def test_advance_does_not_click_omitir(self):
        """Correspondence: pulsar Omitir dejaba la conversación Omitida a 0%.

        Tras el paso 10 el botón decía Omitir. El clic saltaba el árbol y la
        captura siguiente era ya el carrusel de vocabulario.
        """
        page = _Page(avanza_tras=99, etiqueta="Omitir")
        assert _avanzar(page) is False
        assert page.boton.clicks == 0

    def test_advance_closes_the_mic_modal_before_clicking_next(self):
        """Prospective Customer: '¡Eso es correcto!' y el modal tapa Próximo paso."""
        page = _Page(avanza_tras=0)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        called = []

        async def _cerrar():
            called.append(1)
            return False

        speech._dismiss_microphone_check = _cerrar  # type: ignore[method-assign]
        assert asyncio.run(speech._advance_to_next_step(ANTES)) is True
        assert called == [1]

    def test_advance_does_not_click_next_through_the_mic_modal(self):
        """Sin cerrar CalibrationWindow, force-click a Próximo paso no avanza."""
        from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
            _MicNeverCalibrated,
        )

        page = _Page(avanza_tras=0)

        class _Ventana:
            async def count(self):
                return 1

            @property
            def first(self):
                return self

            async def is_visible(self):
                return True

        def _by_id(test_id):
            if test_id == "CalibrationWindow":
                return _Ventana()
            return page.boton

        page.get_by_test_id = _by_id  # type: ignore[method-assign]
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]

        async def _cerrar():
            return False

        speech._dismiss_microphone_check = _cerrar  # type: ignore[method-assign]
        with pytest.raises(_MicNeverCalibrated):
            asyncio.run(speech._advance_to_next_step(ANTES))

    def test_a_mic_modal_that_appears_after_the_answer_retries_not_failed_advance(self):
        """Prospective Customer: el modal sale encima de '¡Eso es correcto!'.

        Si se comprueba CalibrationWindow solo al entrar, se clica Próximo paso
        a través del modal, se anota 'no avanzó' y no hay reintento.
        """
        from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
            _MicNeverCalibrated,
        )

        page = _Page(avanza_tras=99)

        class _VentanaTardia:
            async def count(self):
                return 1 if page.boton.clicks >= 1 else 0

            @property
            def first(self):
                return self

            async def is_visible(self):
                return page.boton.clicks >= 1

        def _by_id(test_id):
            if test_id == "CalibrationWindow":
                return _VentanaTardia()
            return page.boton

        page.get_by_test_id = _by_id  # type: ignore[method-assign]
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        speech.cargo_wav = False

        async def _cerrar():
            return False

        async def _load():
            speech.cargo_wav = True

        speech._dismiss_microphone_check = _cerrar  # type: ignore[method-assign]
        speech._load_mic_check_audio = _load  # type: ignore[method-assign]
        with pytest.raises(_MicNeverCalibrated):
            asyncio.run(speech._advance_to_next_step(ANTES))
        assert speech.cargo_wav is True
        assert page.boton.clicks >= 1

