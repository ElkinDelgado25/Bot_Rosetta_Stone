"""El micrófono que no calibra se reintenta; el resto de fallos, no.

Medido contra la cuenta viva el 02-09-2026: el reconocedor de Rosetta a veces
entra en un bucle de cancelación de calibración —en la consola de la traza,
"Canceling saga calibrateSaga ... [SRE_CANCEL_SESSION]" repetido durante los
90 s— y el micrófono nunca se habilita. Es intermitente: la conversación
siguiente calibra bien con el mismo código. Reabrir la actividad re-dispara la
calibración, así que la conversación se reintenta en vez de perderse.
"""

import asyncio

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
    _MicNeverCalibrated,
)


class _EspiaReintento(PlaywrightFluencySpeechPage):
    """Sustituye ``_complete_activity`` para contar intentos, sin navegador."""

    def __init__(self, resultados, mic_retries=2):
        # page=None: no se toca; sobreescribimos todo lo que lo usaría.
        super().__init__(page=None, mic_retries=mic_retries)  # type: ignore[arg-type]
        self._resultados = list(resultados)
        self.intentos = 0

    async def _start_trace(self):
        return False

    async def _stop_trace(self, tracing, activity_id, completed):
        return None

    async def _complete_activity(self, **kwargs):
        self.intentos += 1
        siguiente = self._resultados.pop(0)
        if isinstance(siguiente, Exception):
            raise siguiente
        return siguiente


def _correr(espia):
    return asyncio.run(
        espia.complete_activity(
            course_title="Curso",
            lesson_title="Lección",
            activity_id="a1",
            expected_steps=5,
        )
    )


class TestReintentoDeMicrofono:
    def test_calibra_al_segundo_intento(self):
        """Primer intento: mic sin calibrar. Segundo: cierra."""
        espia = _EspiaReintento([_MicNeverCalibrated(), True])
        assert _correr(espia) is True
        assert espia.intentos == 2

    def test_se_rinde_tras_agotar_los_reintentos(self):
        espia = _EspiaReintento(
            [_MicNeverCalibrated(), _MicNeverCalibrated(), _MicNeverCalibrated()],
            mic_retries=2,
        )
        assert _correr(espia) is False
        assert espia.intentos == 3  # 1 + 2 reintentos

    def test_un_exito_no_reintenta(self):
        espia = _EspiaReintento([True])
        assert _correr(espia) is True
        assert espia.intentos == 1

    def test_un_fallo_normal_no_se_reintenta(self):
        """Solo el micrófono se repite; un False cualquiera se respeta."""
        espia = _EspiaReintento([False, True])
        assert _correr(espia) is False
        assert espia.intentos == 1

    def test_el_presupuesto_de_espera_no_crece(self):
        """3 intentos de timeout/3: mismo peor caso que 1 de 90 s."""
        espia = _EspiaReintento([True], mic_retries=2)
        assert espia.mic_enable_timeout_ms == espia.timeout_ms // 3
        # Con 0 reintentos, un solo intento con el timeout entero.
        solo = _EspiaReintento([True], mic_retries=0)
        assert solo.mic_enable_timeout_ms == solo.timeout_ms

