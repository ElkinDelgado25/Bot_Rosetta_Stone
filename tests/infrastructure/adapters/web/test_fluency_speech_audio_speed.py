"""El audio del reproductor se acelera; el del micrófono virtual, no.

Lo que más tiempo real se lleva una conversación no es ninguna espera nuestra:
es el reproductor sonando. Cada paso suelta el enunciado y luego la respuesta
del altavoz, y mientras suenan el micrófono está deshabilitado y no hay nada
que hacer salvo esperar. Acelerarlo recorta la corrida de verdad.

La línea que no se puede cruzar es el audio que se le inyecta al reconocedor:
si esa voz va al doble de velocidad, no la entiende. Por eso el gancho excluye
lo que sale de *nuestro* AudioContext (``__rosettaMicContext``) y, por si
acaso, lo que venga marcado con ``__rosettaNoSpeed``.
"""

import re

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page import (
    fluency_speech_page as modulo,
)
from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
    _audio_speed_script,
)


class TestVelocidadPorEntorno:
    def test_por_defecto_va_acelerado(self, monkeypatch):
        monkeypatch.delenv("FLUENCY_AUDIO_SPEED", raising=False)
        page = PlaywrightFluencySpeechPage(object())  # type: ignore[arg-type]
        assert page.audio_speed == modulo._DEFAULT_AUDIO_SPEED > 1

    def test_uno_lo_deja_como_estaba(self, monkeypatch):
        monkeypatch.setenv("FLUENCY_AUDIO_SPEED", "1")
        page = PlaywrightFluencySpeechPage(object())  # type: ignore[arg-type]
        assert page.audio_speed == 1.0

    def test_se_acota_a_lo_que_el_navegador_respeta(self, monkeypatch):
        """Por encima de 4x Chromium deja de reproducir en vez de ir más rápido."""
        monkeypatch.setenv("FLUENCY_AUDIO_SPEED", "50")
        assert PlaywrightFluencySpeechPage(object()).audio_speed == 4.0  # type: ignore[arg-type]
        monkeypatch.setenv("FLUENCY_AUDIO_SPEED", "0.25")
        assert PlaywrightFluencySpeechPage(object()).audio_speed == 1.0  # type: ignore[arg-type]

    def test_un_valor_ilegible_no_tumba_la_corrida(self, monkeypatch):
        monkeypatch.setenv("FLUENCY_AUDIO_SPEED", "rápido")
        page = PlaywrightFluencySpeechPage(object())  # type: ignore[arg-type]
        assert page.audio_speed == modulo._DEFAULT_AUDIO_SPEED


class TestGuionInyectado:
    def test_el_guion_deja_la_velocidad_donde_los_ganchos_la_leen(self):
        assert _audio_speed_script(2.5) == "window.__rosettaAudioSpeed = 2.5;"

    def test_los_ganchos_la_leen_de_forma_perezosa(self):
        """Sin el guion, velocidad normal — no un fallo por variable ausente.

        Los tres guiones se instalan por separado; que el orden importe sería
        una forma nueva de romperse.
        """
        for guion in (modulo._REFERENCE_AUDIO_CAPTURE_SCRIPT,):
            assert "window.__rosettaAudioSpeed || 1" in guion

    def test_el_microfono_virtual_queda_fuera(self):
        """Acelerar lo que oye el reconocedor es garantizar que no lo entienda."""
        gancho = modulo._REFERENCE_AUDIO_CAPTURE_SCRIPT
        assert "this.context !== window.__rosettaMicContext" in gancho
        assert "this.__rosettaNoSpeed" in gancho
        # Las dos marcas tienen que ponerlas de verdad en el otro guion.
        assert "window.__rosettaMicContext = state.context;" in modulo._VIRTUAL_MIC_SCRIPT
        assert re.search(
            r"source\.__rosettaNoSpeed = true", modulo._VIRTUAL_MIC_SCRIPT
        )

    def test_se_acelera_por_las_dos_vias_de_reproduccion(self):
        """El reproductor suena por Web Audio y por <audio>: valen las dos."""
        gancho = modulo._REFERENCE_AUDIO_CAPTURE_SCRIPT
        assert "this.playbackRate.value = factor;" in gancho  # AudioBufferSourceNode
        assert "this.playbackRate = factor;" in gancho  # HTMLMediaElement
