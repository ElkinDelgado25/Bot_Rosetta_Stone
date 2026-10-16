"""La ventana de calibración sale del mismo presupuesto que el micrófono.

Las dos esperas miden el mismo fallo —el SRE no termina de calibrar—, pero la
de la ventana tenía sus 90 s por libre: poner
``FLUENCY_MIC_ENABLE_TIMEOUT_MS=8000`` para fallar rápido bajaba la espera del
botón y dejaba esta entera, así que "fallar rápido" no fallaba rápido.

Si la ventana no se va, no se puede seguir: tapa la actividad (z-index 7000)
y el botón de micrófono sigue deshabilitado. Eso se reintenta reabriendo.
"""

import asyncio

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
    _MicNeverCalibrated,
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


class _Vacio:
    async def count(self):
        return 0

    @property
    def first(self):
        return self

    def locator(self, selector):
        return self


class _PaginaModalAbierto:
    """La comprobación se queda en 'Diga lo siguiente: 1 2 3 4 5'."""

    async def evaluate(self, expression, *args):
        if "__rosettaMicCheckState" in str(expression):
            return {
                "presente": True,
                "escuchando": True,
                "encendidas": 10,
                "barras": 10,
                "senal": True,
                "modo": "tone",
                "texto": "Comprobando el micrófono...Diga lo siguiente:1 2 3 4 5",
            }
        return False

    async def wait_for_function(self, expression, arg=None, timeout=None):
        raise PlaywrightTimeoutError("CalibrationWindow sigue")

    def locator(self, selector):
        return _Vacio()

    def get_by_role(self, *args, **kwargs):
        return _Vacio()

    def get_by_test_id(self, test_id):
        return _Vacio()

    def get_by_text(self, pattern):
        return _Vacio()

    async def screenshot(self, path=None):
        return None


class TestDismissQueNoCierra:
    def test_una_ventana_abierta_no_es_exito(self):
        """Seguir debajo del modal era clicar contra z-index 7000."""
        speech = PlaywrightFluencySpeechPage(_PaginaModalAbierto())  # type: ignore[arg-type]
        with pytest.raises(_MicNeverCalibrated):
            asyncio.run(speech._dismiss_microphone_check())

    def test_no_entra_a_los_pasos_si_el_modal_sigue(self):
        class _PaginaActividad(_PaginaModalAbierto):
            class _Loc:
                async def count(self):
                    return 0

                @property
                def first(self):
                    return self

                @property
                def last(self):
                    return self

                async def wait_for(self, **kwargs):
                    return None

                async def click(self, **kwargs):
                    return None

            class _Ctx:
                async def grant_permissions(self, permisos, origin=None):
                    return None

            context = _Ctx()

            def locator(self, selector):
                return self._Loc()

            def get_by_test_id(self, test_id):
                return self._Loc()

            async def add_init_script(self, script):
                return None

        speech = PlaywrightFluencySpeechPage(_PaginaActividad())  # type: ignore[arg-type]

        async def _open(*_a, **_k):
            return None

        async def _modo():
            return "hablar"

        async def _load():
            return None

        async def _engine():
            return True

        speech._open_lesson = _open  # type: ignore[method-assign]
        speech._input_mode = _modo  # type: ignore[method-assign]
        speech._load_mic_check_audio = _load  # type: ignore[method-assign]
        speech._wait_for_speech_engine = _engine  # type: ignore[method-assign]
        with pytest.raises(_MicNeverCalibrated):
            asyncio.run(
                speech._complete_activity(
                    course_title="C",
                    lesson_title="L",
                    activity_id="a1",
                    expected_steps=3,
                )
            )
