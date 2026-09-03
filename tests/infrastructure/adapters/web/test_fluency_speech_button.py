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
    _MicNeverCalibrated,
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
        # El micrófono que no se habilita pide reintento (calibración
        # intermitente del SRE), no un timeout genérico: por eso _MicNeverCalibrated.
        with pytest.raises(_MicNeverCalibrated):
            asyncio.run(_speech(page)._click_speech_button())
        # El diagnóstico mira el DOM antes de rendirse.
        assert any("outerHTML" in e for e in page.evaluated)
        assert page.button.clicked is False


def _con_ruido(page, monkeypatch, valor="1"):
    monkeypatch.setenv("FLUENCY_MIC_CALIBRATION_NOISE", valor)
    return PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]


class TestRuidoDeCalibracion:
    """Da señal al reconocedor mientras calibra, para que no cancele en bucle.

    Medido en la traza (02-09-2026): con el micrófono virtual en silencio, la
    calibración por-paso lanza SRE_CANCEL_SESSION durante los 90 s y el botón no
    se habilita. Los 8 cancels caen entre +9.7s y +38.4s, todos antes de que se
    inyecte audio: el reconocedor no encuentra señal y cancela.
    """

    def test_arranca_la_senal_antes_de_esperar_el_boton(self, monkeypatch):
        page = _Page()
        asyncio.run(_con_ruido(page, monkeypatch)._click_speech_button())
        arranques = [e for e in page.evaluated if "StartCalibrationNoise" in e]
        assert arranques, "no se dio señal durante la calibración"

    def test_corta_la_senal_al_habilitarse_el_boton_antes_de_grabar(self, monkeypatch):
        page = _Page()
        asyncio.run(_con_ruido(page, monkeypatch)._click_speech_button())
        cortes = [e for e in page.evaluated if "StopCalibrationNoise" in e]
        assert cortes, "la señal no se cortó antes de grabar la respuesta"
        assert page.button.clicked

    def test_corta_la_senal_tambien_cuando_el_microfono_no_calibra(self, monkeypatch):
        page = _Page(falla="SpeechButton")
        with pytest.raises(_MicNeverCalibrated):
            asyncio.run(_con_ruido(page, monkeypatch)._click_speech_button())
        # Aunque falle, la señal no puede quedarse sonando en la siguiente vuelta.
        assert any("StopCalibrationNoise" in e for e in page.evaluated)

    def test_apagable_por_env(self, monkeypatch):
        page = _Page()
        asyncio.run(_con_ruido(page, monkeypatch, valor="0")._click_speech_button())
        assert not any("CalibrationNoise" in e for e in page.evaluated)
        assert page.button.clicked  # sin señal sigue funcionando el resto del flujo

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
