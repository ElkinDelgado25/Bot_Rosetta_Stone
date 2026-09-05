"""La ventana de calibración sale del mismo presupuesto que el micrófono.

Las dos esperas miden el mismo fallo —el SRE no termina de calibrar—, pero la
de la ventana tenía sus 90 s por libre: poner
``FLUENCY_MIC_ENABLE_TIMEOUT_MS=8000`` para fallar rápido bajaba la espera del
botón y dejaba esta entera, así que "fallar rápido" no fallaba rápido.
"""

import asyncio

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Page:
    def __init__(self):
        self.esperas = []

    async def wait_for_function(self, expression, arg=None, timeout=None):
        self.esperas.append(timeout)

    async def evaluate(self, expression, arg=None):
        return None


def _esperar(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    assert asyncio.run(speech._wait_for_mic_check_to_pass()) is True
    return speech


class TestPresupuestoDeCalibracion:
    def test_no_gasta_el_timeout_largo_por_su_cuenta(self, monkeypatch):
        monkeypatch.delenv("FLUENCY_MIC_ENABLE_TIMEOUT_MS", raising=False)
        monkeypatch.delenv("FLUENCY_MIC_RETRIES", raising=False)
        page = _Page()
        speech = _esperar(page)
        assert page.esperas == [speech.mic_enable_timeout_ms]
        assert speech.mic_enable_timeout_ms < speech.timeout_ms

    def test_fallar_rapido_tambien_acorta_esta(self, monkeypatch):
        monkeypatch.setenv("FLUENCY_MIC_ENABLE_TIMEOUT_MS", "8000")
        page = _Page()
        _esperar(page)
        assert page.esperas == [8000]
