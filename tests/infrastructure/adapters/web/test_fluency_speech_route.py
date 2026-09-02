"""El cableado de la conversación: qué ruta se toma y qué se salta.

Las piezas sueltas ya tienen sus tests (``_input_mode``, ``_another_step_starts``,
el avance de paso). Lo que no tenía ninguno es ``_complete_activity``, que es
justo donde vivía el error que costó dos semanas: ``DialogueExpressionWithoutReco``
se enrutó a la ruta de voz **sin adaptarla**, así que esperó un micrófono que esa
actividad no tiene, agotó 90 s y se anotó como imposible.

Ese fallo no lo habría visto ningún test de pieza: cada una funcionaba. Lo que
estaba mal era cuál se llamaba. Esto cubre exactamente eso.
"""

import asyncio

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Locator:
    def __init__(self, coincidencias=1):
        self.coincidencias = coincidencias

    @property
    def first(self):
        return self

    async def count(self):
        return self.coincidencias

    async def wait_for(self, state=None, timeout=None):
        return None

    async def click(self, **kwargs):
        return None


class _Context:
    async def grant_permissions(self, permisos, origin=None):
        return None


class _Page:
    """Lo justo para que ``_complete_activity`` llegue al reparto de modos."""

    context = _Context()

    def __init__(self, *, ya_completa=False):
        self.ya_completa = ya_completa

    def locator(self, selector):
        return _Locator(1 if self.ya_completa else 0)

    def get_by_test_id(self, test_id):
        return _Locator()

    async def add_init_script(self, script):
        return None

    async def evaluate(self, script, arg=None):
        return None


class _Espia(PlaywrightFluencySpeechPage):
    """La página real con las hojas sustituidas: se mira a quién llama."""

    def __init__(self, page, *, modo, pasos_ok=True, turnos=99):
        super().__init__(page)  # type: ignore[arg-type]
        self._modo = modo
        self._pasos_ok = pasos_ok
        self._turnos = turnos
        self.hablados = []
        self.elegidos = []
        self.modos_preguntados = []
        self.preparo_microfono = False

    async def _open_lesson(self, course_title, lesson_title):
        return None

    async def _input_mode(self):
        return self._modo

    async def _load_mic_check_audio(self):
        self.preparo_microfono = True

    async def _dismiss_microphone_check(self):
        self.preparo_microfono = True

    async def _complete_visible_step(self, step_number):
        self.hablados.append(step_number)
        return self._pasos_ok

    async def _complete_visible_choice_step(self, step_number):
        self.elegidos.append(step_number)
        return self._pasos_ok

    async def _another_step_starts(self, step_number, modo="hablar"):
        self.modos_preguntados.append(modo)
        return step_number < self._turnos


def _correr(espia, pasos=3):
    return asyncio.run(
        espia._complete_activity(
            course_title="Curso",
            lesson_title="Lección",
            activity_id="a1",
            expected_steps=pasos,
        )
    )


class TestRutaDeLaConversacion:
    def test_sin_microfono_se_responde_eligiendo(self):
        """El caso que estaba roto: no puede acabar en la ruta hablada."""
        espia = _Espia(_Page(), modo="elegir")
        assert _correr(espia) is True
        assert espia.elegidos == [1, 2, 3]
        assert espia.hablados == []

    def test_sin_microfono_no_se_monta_el_microfono(self):
        """Montarlo era lo que gastaba los 90 s antes de rendirse."""
        espia = _Espia(_Page(), modo="elegir")
        _correr(espia)
        assert espia.preparo_microfono is False

    def test_el_modo_viaja_a_la_pregunta_de_si_queda_otro_turno(self):
        """Preguntando por el micrófono, toda WithoutReco moría en su paso 1."""
        espia = _Espia(_Page(), modo="elegir")
        _correr(espia)
        assert set(espia.modos_preguntados) == {"elegir"}

    def test_con_microfono_se_habla_y_se_monta_el_microfono(self):
        espia = _Espia(_Page(), modo="hablar")
        assert _correr(espia) is True
        assert espia.hablados == [1, 2, 3]
        assert espia.elegidos == []
        assert espia.preparo_microfono is True
        assert set(espia.modos_preguntados) == {"hablar"}

    def test_sin_microfono_ni_respuestas_no_hay_nada_que_contestar(self):
        espia = _Espia(_Page(), modo="desconocido")
        assert _correr(espia) is False
        assert espia.hablados == []
        assert espia.elegidos == []

    def test_una_conversacion_mas_corta_de_lo_declarado_no_es_un_fallo(self):
        """``expected_steps`` es cota superior: 13 declarados, 10 reales."""
        espia = _Espia(_Page(), modo="elegir", turnos=2)
        assert _correr(espia, pasos=13) is True
        assert espia.elegidos == [1, 2]

    def test_un_paso_que_no_se_resuelve_hunde_la_actividad(self):
        espia = _Espia(_Page(), modo="elegir", pasos_ok=False)
        assert _correr(espia) is False
        assert espia.elegidos == [1]

    def test_una_actividad_ya_completa_no_se_vuelve_a_hacer(self):
        espia = _Espia(_Page(ya_completa=True), modo="elegir")
        assert _correr(espia) is True
        assert espia.elegidos == []
