"""``expected_steps`` no coincide con lo que pinta el reproductor.

Medido en una corrida real: una actividad que la API declaraba de 13 pasos
tenía 10 enunciados. Al acabar el décimo se esperaban 90 s a un micrófono que
ya no vuelve y la conversación —terminada, y al 100% según ``getProgress``— se
daba por fallida y no se persistía.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Boton:
    def __init__(self, aparece=True):
        self.aparece = aparece
        self.esperas = []

    async def wait_for(self, state=None, timeout=None):
        self.esperas.append(timeout)
        if not self.aparece:
            raise PlaywrightTimeoutError("no vuelve")


class _Page:
    def __init__(self, aparece=True):
        self.boton = _Boton(aparece)

    def get_by_test_id(self, test_id):
        return self.boton


def _hay_otro(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._another_step_starts(10))


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
