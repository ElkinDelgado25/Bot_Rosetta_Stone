"""Pulsar el micrófono en el momento en que se puede pulsar.

De la traza de una actividad fallida: el reproductor deja el botón
``disabled`` mientras suena audio suyo, y el audio que sonaba era el nuestro
(hay que pulsar el altavoz para capturar la respuesta de referencia). Esperar
al botón sin esperar antes al audio agotaba los 90 s.
"""

import asyncio

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Button:

    def __init__(self):
        self.clicked = False


    @property
    def first(self):
        """Un locator de verdad siempre lo ofrece; el código lo usa."""
        return self
    async def wait_for(self, state=None, timeout=None):
        return None

    async def click(self, **kwargs):
        self.clicked = True


class _Page:
    def __init__(self, falla=None):
        self.button = _Button()
        self.waits = []
        self.falla = falla
        self.evaluated = []

    def get_by_test_id(self, test_id):
        return self.button

    async def wait_for_function(self, expression, *args, **kwargs):
        self.waits.append(expression)
        if self.falla and self.falla in expression:
            raise PlaywrightTimeoutError("agotado")

    async def evaluate(self, expression, *args):
        self.evaluated.append(expression)
        return {"existe": True, "html": "<div disabled>", "audio": True}


def _speech(page):
    return PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]


class TestSpeechButton:
    def test_waits_for_the_audio_before_the_button(self):
        page = _Page()
        asyncio.run(_speech(page)._click_speech_button())
        assert len(page.waits) == 2
        # Primero que calle el audio, después que el botón se habilite.
        assert "audio_playing" in page.waits[0]
        assert "SpeechButton" in page.waits[1]
        assert page.button.clicked

    def test_a_button_that_never_enables_reports_its_state(self):
        page = _Page(falla="SpeechButton")
        with pytest.raises(PlaywrightTimeoutError):
            asyncio.run(_speech(page)._click_speech_button())
        # El diagnóstico mira el DOM antes de rendirse.
        assert any("outerHTML" in e for e in page.evaluated)
        assert page.button.clicked is False

    def test_audio_that_never_stops_still_lets_the_button_decide(self):
        """Este test decía lo contrario, y estaba de más.

        Esperar el audio se puso por una razón de orden: hacerlo antes evita
        que la espera del botón queme sus 90 s mientras suena algo. Esa razón
        sigue viva y el orden no cambia. Lo que no se sostenía es tratar el
        audio atascado como el final de la actividad: quien decide si se puede
        hablar es el botón, y tiene su propia espera con su propio diagnóstico.

        Costó una actividad en la corrida del 02-09-2026 a las 10:29 — "Se
        agotó la espera de: que el reproductor deje de reproducir audio" — sin
        haber mirado el botón ni una vez.
        """
        page = _Page(falla="audio_playing")
        asyncio.run(_speech(page)._click_speech_button())
        assert len(page.waits) == 2
        assert "audio_playing" in page.waits[0]
        assert "SpeechButton" in page.waits[1]
        assert page.button.clicked
