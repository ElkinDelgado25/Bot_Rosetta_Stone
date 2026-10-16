"""La grabación real para la comprobación de micrófono.

La prueba pide decir "1, 2, 3, 4, 5" y escucha de verdad. Un tono llena el
medidor y el reconocedor no lo acepta. Tiene que haber voz; si no, se reintenta
reabriendo la actividad, no se sigue con el modal abierto.
"""

import asyncio
import base64

import pytest

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page import (
    fluency_speech_page as modulo,
)
from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
    _MicNeverCalibrated,
)


class _Page:
    def __init__(self, resultado=True):
        self.resultado = resultado
        self.recibido = None

    async def evaluate(self, expression, *args):
        if args:
            self.recibido = args[0]
        return self.resultado


def _cargar(page, tmp_path, monkeypatch, nombre="mic_check.wav", datos=b"RIFFtest"):
    carpeta = tmp_path / "audio"
    carpeta.mkdir(parents=True, exist_ok=True)
    if nombre:
        (carpeta / nombre).write_bytes(datos)
    monkeypatch.setattr(
        "Resolucion_script_rosseta.infraestructura.core.get_base_dir", lambda: tmp_path
    )
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    asyncio.run(speech._load_mic_check_audio())
    return speech


class TestMicCheckAudio:
    def test_the_recording_reaches_the_page_encoded(self, tmp_path, monkeypatch):
        page = _Page()
        _cargar(page, tmp_path, monkeypatch, datos=b"RIFFhola")
        assert page.recibido == base64.b64encode(b"RIFFhola").decode()

    def test_other_formats_are_accepted(self, tmp_path, monkeypatch):
        page = _Page()
        _cargar(page, tmp_path, monkeypatch, nombre="mic_check.mp3")
        assert page.recibido is not None

    def test_without_a_home_recording_uses_the_packaged_one(self, tmp_path, monkeypatch):
        page = _Page()
        _cargar(page, tmp_path, monkeypatch, nombre=None)
        assert page.recibido is not None

    def test_without_any_recording_the_check_is_retried(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "Resolucion_script_rosseta.infraestructura.core.get_base_dir",
            lambda: tmp_path,
        )
        speech = PlaywrightFluencySpeechPage(_Page())  # type: ignore[arg-type]
        monkeypatch.setattr(speech, "_packaged_mic_check_files", lambda: ())
        with pytest.raises(_MicNeverCalibrated):
            asyncio.run(speech._load_mic_check_audio())


class TestMicCheckPlayback:
    def test_the_recording_is_preferred_and_the_tone_is_not_a_fallback(self):
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "__rosettaMicCheckBuffer" in guion
        assert 'window.__rosettaMicCheckMode = "tone"' not in guion

    def test_the_recording_loops(self):
        # La comprobación dura más que la grabación.
        assert "fuente.loop = true" in modulo._VIRTUAL_MIC_SCRIPT
