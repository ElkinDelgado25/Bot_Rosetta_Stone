"""Esperar el silencio no puede depender de que suene un solo altavoz.

Medido en una corrida real (02-09-2026): en un paso pueden estar sonando **dos**
``audio_playing`` a la vez — el del enunciado y el de la respuesta recién
pulsada. Se esperaba con un locator, que con dos coincidencias hace saltar el
modo estricto de Playwright; y como ocurre a mitad de la conversación, se
llevaba por delante la actividad entera con un "Speech browser flow failed" que
no menciona el audio por ninguna parte.

``count()`` no avisa del choque: devuelve 2, el ``if`` pasa, y revienta el
``wait_for``. Es la misma trampa que ya está documentada para Stories.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _LocatorEstricto:
    """Como Playwright: con más de una coincidencia, esperar es un error."""

    def __init__(self, coincidencias):
        self.coincidencias = coincidencias

    async def count(self):
        return self.coincidencias

    async def wait_for(self, state=None, timeout=None):
        if self.coincidencias > 1:
            raise AssertionError(
                "strict mode violation: resolved to %d elements" % self.coincidencias
            )


class _Page:
    def __init__(self, coincidencias=2, se_calla=True):
        self.coincidencias = coincidencias
        self.se_calla = se_calla
        self.expresiones = []

    def locator(self, selector):
        return _LocatorEstricto(self.coincidencias)

    async def wait_for_function(self, expression, timeout=None, arg=None):
        self.expresiones.append(expression)
        if not self.se_calla:
            raise PlaywrightTimeoutError("sigue sonando")


def _esperar(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._wait_for_all_audio_to_stop())


class TestEsperarSilencio:
    def test_two_speakers_playing_is_not_an_error(self):
        """El caso que tumbaba la conversación: dos altavoces a la vez."""
        page = _Page(coincidencias=2)
        _esperar(page)
        assert page.expresiones, "no se esperó por la condición en JS"

    def test_it_waits_for_all_of_them_not_just_the_first(self):
        """Queremos silencio, no que se vaya el primero de los dos."""
        page = _Page(coincidencias=2)
        _esperar(page)
        assert "!document.querySelector('[data-qa=audio_playing]')" in (
            page.expresiones[0]
        )

    def test_audio_that_never_stops_does_not_sink_the_activity(self):
        page = _Page(coincidencias=1, se_calla=False)
        _esperar(page)  # no debe propagar


class _PageQueNoSeCalla:
    """El audio nunca para, pero el micrófono está perfectamente listo."""

    def __init__(self):
        self.esperas = []

    async def wait_for_function(self, expression, timeout=None, arg=None):
        self.esperas.append((expression, timeout))
        if "audio_playing" in expression:
            raise PlaywrightTimeoutError("sigue sonando")
        return None


class _Boton:
    def __init__(self):
        self.pulsado = False

    @property
    def first(self):
        return self

    async def wait_for(self, state=None, timeout=None):
        return None

    async def click(self, **kwargs):
        self.pulsado = True


class _PageAudioAtascadoBotonListo(_PageQueNoSeCalla):
    """El audio nunca se calla, pero el micrófono sí está habilitado."""

    def __init__(self):
        super().__init__()
        self.boton = _Boton()

    def get_by_test_id(self, test_id):
        return self.boton


class TestElAudioAtascadoNoMataLaActividad:
    """Medido el 02-09-2026 a las 10:29: una actividad perdida por esto.

    "Se agotó la espera de: que el reproductor deje de reproducir audio", y sin
    haber mirado nunca el botón — que es lo único que decide si se puede hablar.
    La misma condición se esperaba en dos sitios del archivo con criterios
    opuestos: aquí era fatal, en ``_wait_for_all_audio_to_stop`` era benigna.
    """

    def test_un_audio_que_no_para_no_levanta_excepcion(self):
        page = _PageQueNoSeCalla()
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._wait_for_all_audio_to_stop(timeout_ms=speech.probe_timeout_ms))

    def test_como_condicion_previa_usa_la_sonda_corta(self):
        """No puede costar lo mismo que una espera de verdad: no es el veredicto."""
        page = _PageQueNoSeCalla()
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._wait_for_all_audio_to_stop(timeout_ms=speech.probe_timeout_ms))
        assert page.esperas[0][1] == speech.probe_timeout_ms
        assert page.esperas[0][1] < speech.timeout_ms


class TestPulsarElMicrofonoConAudioAtascado:
    def test_se_pulsa_el_microfono_aunque_el_audio_no_pare(self):
        """El arreglo de verdad: antes esto perdía la actividad sin mirar el botón."""
        page = _PageAudioAtascadoBotonListo()
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._click_speech_button())
        assert page.boton.pulsado is True

    def test_la_espera_de_audio_no_gasta_el_timeout_largo(self):
        page = _PageAudioAtascadoBotonListo()
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._click_speech_button())
        de_audio = [t for e, t in page.esperas if "audio_playing" in e]
        assert de_audio == [speech.probe_timeout_ms]


class TestNoSeEsperaNoventaSegundosPorNada:
    """Medido en la traza de la actividad del 02-09-2026 a las 10:23.

    La condición ``!audio_playing`` se agotó **dos veces** con el timeout
    largo: 180 s de espera muerta en una sola actividad, terminando igual que
    si no se hubiera esperado. O se calla enseguida o no se calla.
    """

    def test_por_defecto_usa_la_sonda_corta_no_los_noventa_segundos(self):
        page = _PageQueNoSeCalla()
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._wait_for_all_audio_to_stop())
        assert page.esperas[0][1] == speech.probe_timeout_ms
        assert page.esperas[0][1] < speech.timeout_ms
