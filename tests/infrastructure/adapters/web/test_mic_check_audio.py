"""La grabación real para la comprobación de micrófono.

La prueba pide decir "1, 2, 3, 4, 5" y escucha de verdad. Una voz humana la
pasa; un tono puede que sí y puede que no. Si el archivo está, se usa; si no,
la corrida sigue igual con el tono.
"""

import asyncio
import base64

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page import (
    fluency_speech_page as modulo,
)
from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
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


class TestMicCheckAudio:
    def test_the_recording_reaches_the_page_encoded(self, tmp_path, monkeypatch):
        page = _Page()
        _cargar(page, tmp_path, monkeypatch, datos=b"RIFFhola")
        assert page.recibido == base64.b64encode(b"RIFFhola").decode()

    def test_other_formats_are_accepted(self, tmp_path, monkeypatch):
        page = _Page()
        _cargar(page, tmp_path, monkeypatch, nombre="mic_check.mp3")
        assert page.recibido is not None

    def test_without_a_recording_nothing_breaks(self, tmp_path, monkeypatch):
        page = _Page()
        _cargar(page, tmp_path, monkeypatch, nombre=None)
        assert page.recibido is None


class TestMicCheckPlayback:
    def test_a_real_recording_wins_over_the_tone(self):
        guion = modulo._VIRTUAL_MIC_SCRIPT
        buffer = guion.index("__rosettaMicCheckBuffer")
        oscilador = guion.index("createOscillator")
        assert buffer < oscilador

    def test_the_recording_loops(self):
        # La comprobación dura más que la grabación.
        assert "fuente.loop = true" in modulo._VIRTUAL_MIC_SCRIPT

