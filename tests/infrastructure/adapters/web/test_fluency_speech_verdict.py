"""Qué dice el botón de enviar después de hablar.

Mientras el paso está sin resolver solo tiene dos textos, y se sacaron de la
traza de una corrida real (``data-qa-button-text``):

- **"Omitir"** — no ha oído nada.
- **"Volver a intentar"** — ha oído y no ha entendido.

Dar por buena "cualquier cosa que no sea Omitir" hacía pulsar *Volver a
intentar*, que reinicia el paso: el reproductor volvía al principio, el
enunciado no cambiaba nunca y la espera moría a los 90 s señalando al sitio
equivocado.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Page:
    def __init__(self, etiqueta="Continuar", responde=True):
        self.etiqueta = etiqueta
        self.responde = responde
        self.consultado = []

    async def wait_for_function(self, expression, *, arg=None, timeout=None):
        self.consultado.append(expression)
        if not self.responde:
            raise PlaywrightTimeoutError("sigue en Omitir")

    async def evaluate(self, expression, *args):
        return self.etiqueta


def _verdict(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._submit_verdict())


class TestSubmitVerdict:
    def test_still_on_skip_means_it_heard_nothing(self):
        assert _verdict(_Page(responde=False)) == "sin respuesta"

    def test_try_again_is_a_rejection_not_a_green_light(self):
        assert _verdict(_Page(etiqueta="Volver a intentar")) == "rechazada"

    def test_the_english_label_too(self):
        assert _verdict(_Page(etiqueta="Try again")) == "rechazada"

    def test_anything_else_is_the_answer_going_through(self):
        assert _verdict(_Page(etiqueta="Continuar")) == "aceptada"

    def test_it_reads_the_data_qa_label(self):
        """El texto visible puede llevar adornos; el atributo, no."""
        page = _Page()
        _verdict(page)
        assert "data-qa-button-text" in page.consultado[-1]

    def test_it_does_not_wait_the_long_timeout(self):
        """No haber oído nada es lo normal cuando algo va mal: no son 90 s."""
        page = _Page(responde=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._submit_verdict())
        assert speech.probe_timeout_ms < speech.timeout_ms
