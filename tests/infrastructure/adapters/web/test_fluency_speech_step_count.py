"""``expected_steps`` no coincide con lo que pinta el reproductor.

Medido en una corrida real: una actividad que la API declaraba de 13 pasos
tenía 10 enunciados. Al acabar el décimo se esperaban 90 s a un micrófono que
ya no vuelve y la conversación —terminada, y al 100% según ``getProgress``— se
daba por fallida y no se persistía.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Boton:
    """Un localizador de mentira. ``first`` existe porque las respuestas son
    tres: sin él, esperar por ``ChoiceButton`` rompe el modo estricto."""

    def __init__(self, aparece=True):
        self.aparece = aparece
        self.esperas = []

    @property
    def first(self):
        return self

    async def wait_for(self, state=None, timeout=None):
        self.esperas.append(timeout)
        if not self.aparece:
            raise PlaywrightTimeoutError("no vuelve")


class _Page:
    def __init__(self, aparece=True):
        self.boton = _Boton(aparece)
        self.pedidos = []

    def get_by_test_id(self, test_id):
        self.pedidos.append(test_id)
        return self.boton


def _hay_otro(page, modo="hablar"):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._another_step_starts(10, modo))


class TestStepCount:
    def test_the_microphone_coming_back_means_another_step(self):
        assert _hay_otro(_Page(aparece=True)) is True

    def test_no_microphone_means_the_conversation_ended(self):
        assert _hay_otro(_Page(aparece=False)) is False

    def test_finding_out_does_not_cost_the_long_timeout(self):
        """Eran 90 s por actividad, y siempre en la que ya había terminado."""
        page = _Page(aparece=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._another_step_starts(10))
        assert page.boton.esperas == [speech.probe_timeout_ms]
        assert speech.probe_timeout_ms < speech.timeout_ms


class TestStepCountEligiendo:
    """Sin micrófono la señal de "queda otro paso" es otra: las respuestas.

    Preguntar por el micrófono en una conversación que se contesta pulsando da
    siempre que no, así que toda actividad ``WithoutReco`` se daba por acabada
    en su primer paso.
    """

    def test_more_choices_mean_another_step(self):
        page = _Page(aparece=True)
        assert _hay_otro(page, modo="elegir") is True
        assert page.pedidos == ["ChoiceButton"]

    def test_no_more_choices_means_the_conversation_ended(self):
        assert _hay_otro(_Page(aparece=False), modo="elegir") is False

