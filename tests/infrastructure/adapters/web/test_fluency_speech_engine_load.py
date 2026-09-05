"""Se espera a que el motor de habla cargue, y se espera al progreso.

Auditoría del 05-09-2026: "el micrófono no se habilita" no era la calibración.
La captura del instante del timeout muestra el modal parado en "Cargando motor
de habla…28%" — el botón no podía habilitarse porque no había motor. El
presupuesto que se le daba eran 30 s (``timeout_ms // (mic_retries + 1)``) y al
agotarse se reabría la lección, que devuelve la carga a 0 %: tres intentos de
30 s no son 90 s de carga, son tres cargas abortadas.

De ahí las dos reglas que cubren estos tests: mientras el porcentaje **suba** se
sigue esperando por mucho que tarde, y una carga atascada **no se reintenta**.
"""

import asyncio

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _PaginaFalsa:
    """Devuelve una secuencia de estados del motor; no toca navegador."""

    def __init__(self, estados):
        self._estados = list(estados)
        self.esperas_ms = 0

    async def evaluate(self, *_args, **_kwargs):
        if not self._estados:
            return None
        return self._estados.pop(0)

    async def wait_for_timeout(self, ms):
        self.esperas_ms += ms


class _EspiaMotor(PlaywrightFluencySpeechPage):
    def __init__(self, estados, **kwargs):
        super().__init__(page=_PaginaFalsa(estados), **kwargs)  # type: ignore[arg-type]
        self.capturas = []

    async def _dump_screenshot(self, descripcion):
        self.capturas.append(descripcion)


def _cargando(pct):
    return {"cargando": True, "pct": pct, "texto": f"Cargando motor de habla…{pct}%"}


class TestEsperaDelMotorDeHabla:
    def test_sin_modal_no_espera_nada(self):
        """El caso normal —motor ya cargado— no puede costar ni un segundo."""
        espia = _EspiaMotor([None])
        assert asyncio.run(espia._wait_for_speech_engine()) is True
        assert espia.page.esperas_ms == 0

    def test_espera_mientras_el_porcentaje_suba(self):
        """Aunque tarde más que cualquier timeout del micrófono."""
        estados = [_cargando(p) for p in range(0, 100, 2)] + [None]
        espia = _EspiaMotor(estados)
        assert asyncio.run(espia._wait_for_speech_engine()) is True
        assert espia._motor_cargado is True
        # 50 vueltas de un segundo: muy por encima de los 30 s que se le daban.
        assert espia.page.esperas_ms >= 30_000

    def test_se_rinde_si_el_porcentaje_no_avanza(self):
        """Parado en el mismo número: ahí sí hay que cortar."""
        espia = _EspiaMotor([_cargando(28)] * 60, engine_stall_ms=5_000)
        assert asyncio.run(espia._wait_for_speech_engine()) is False
        assert espia._motor_cargado is False
        assert espia.capturas == ["motor_de_habla_parado"]

    def test_el_techo_absoluto_corta_una_carga_eterna(self):
        """Avanza siempre pero no termina nunca: el techo la para igual."""
        estados = [_cargando(p) for p in range(0, 100)] * 5
        espia = _EspiaMotor(estados, engine_timeout_ms=20_000)
        assert asyncio.run(espia._wait_for_speech_engine()) is False
        assert espia.capturas == ["motor_de_habla_lento"]


class TestKnobsDelMotor:
    def test_valores_por_defecto(self):
        espia = _EspiaMotor([None])
        assert espia.engine_timeout_ms == 300_000
        assert espia.engine_stall_ms == 45_000

    def test_el_techo_no_lo_recorta_el_presupuesto_del_microfono(self):
        """Son presupuestos distintos: uno es descarga, el otro calibración."""
        espia = _EspiaMotor([None], timeout_ms=90_000, mic_retries=2)
        assert espia.mic_enable_timeout_ms == 30_000
        assert espia.engine_timeout_ms > espia.mic_enable_timeout_ms
