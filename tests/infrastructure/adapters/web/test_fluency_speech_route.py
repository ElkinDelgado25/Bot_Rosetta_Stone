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

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Locator:
    def __init__(self, coincidencias=1, clicks=None, index=0):
        self.coincidencias = coincidencias
        self.clicks = clicks if clicks is not None else []
        self.index = index

    @property
    def first(self):
        return _Locator(self.coincidencias, self.clicks, 0)

    @property
    def last(self):
        return _Locator(self.coincidencias, self.clicks, max(0, self.coincidencias - 1))

    async def count(self):
        return self.coincidencias

    async def wait_for(self, state=None, timeout=None):
        return None

    async def is_visible(self):
        return True

    def nth(self, i):
        return type(self)(self.coincidencias, self.clicks, i)

    async def click(self, **kwargs):
        self.clicks.append(self.index)


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
        # Hueco aún clickable. Si el mapa ya marcó todas las copias, no queda.
        if test_id == "CalibrationWindow":
            return _Locator(0)
        return _Locator(0 if self.ya_completa else 1)

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
        self.espero_motor = False

    async def _open_lesson(self, course_title, lesson_title):
        return None

    async def _input_mode(self):
        return self._modo

    async def _load_mic_check_audio(self):
        self.preparo_microfono = True

    async def _dismiss_microphone_check(self):
        self.preparo_microfono = True

    async def _wait_for_speech_engine(self):
        self.espero_motor = True
        return True

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

    def test_sin_microfono_prepara_la_voz_de_calibracion(self):
        """Prospective Customer: el modal sale al marcar, no al abrir.

        Esperar el motor/SpeechButton eran los 90 s. Cargar el WAV no.
        Sin él el medidor se queda a 1/10 y Próximo paso no avanza.
        """
        espia = _Espia(_Page(), modo="elegir")
        _correr(espia)
        assert espia.preparo_microfono is True
        assert espia.espero_motor is False

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

    def test_force_replays_an_activity_the_map_already_marks_complete(self):
        """El re-ensayo con ``force`` rejuega aunque el mapa la marque completa.

        Es el caso del diálogo acreditado con bestGrade=0: para subirlo hay que
        volver a jugarlo aunque el mapa ya lo pinte como hecho.
        """
        espia = _Espia(_Page(ya_completa=True), modo="elegir")
        assert (
            asyncio.run(
                espia._complete_activity(
                    course_title="Curso",
                    lesson_title="Lección",
                    activity_id="a1",
                    expected_steps=3,
                    force=True,
                )
            )
            is True
        )
        assert espia.elegidos == [1, 2, 3]

    def test_una_copia_completa_no_salta_la_otra_del_mapa(self):
        """Sales Contact: el diálogo abre y cierra la lección, mismo id.

        Una copia ya tiene ``_completed``; la otra sigue clickable. Saltar
        las dos dejaba countOfActivities en 17 con 16 acreditadas.
        """

        class _MapaConCopiaHueca(_Page):
            def locator(self, selector):
                return _Locator(1)

            def get_by_test_id(self, test_id):
                return _Locator(1)

        espia = _Espia(_MapaConCopiaHueca(), modo="elegir")
        assert _correr(espia) is True
        assert espia.elegidos == [1, 2, 3]

    def test_the_remaining_map_copy_is_the_closing_slot(self):
        """La ranura extra está a la derecha. ``.first`` reabre la de apertura.

        Prospective Customer / Sales Contact: tras acreditar el id, el mapa
        sigue pintando ``activity_{id}`` dos veces. Clicar la de la izquierda
        (ya hecha) deja count 17 con 16 acreditadas.
        """

        class _MapaDosCopias(_Page):
            def __init__(self):
                super().__init__()
                self.clicks = []

            def locator(self, selector):
                return _Locator(1)

            def get_by_test_id(self, test_id):
                if test_id.startswith("activity_"):
                    return _Locator(2, clicks=self.clicks)
                return _Locator(1)

        page = _MapaDosCopias()
        espia = _Espia(page, modo="elegir")
        assert _correr(espia) is True
        assert page.clicks == [1]

    def test_a_locked_closing_slot_is_force_clicked(self):
        """Prospective Customer: la copia de cierre no visible era un skip.

        ``wait_for`` 90 s no. Force-click corto: si el hueco existe en el DOM
        (count gap 16/17) hay que jugarlo, no dar la lección por cerrada.
        """
        class _HuecoInvisible(_Locator):
            async def is_visible(self):
                return False

            async def wait_for(self, state=None, timeout=None):
                from playwright.async_api import TimeoutError as PlaywrightTimeoutError

                raise PlaywrightTimeoutError(f"timeout {timeout}")

        class _MapaCierreBloqueado(_Page):
            def __init__(self):
                super().__init__()
                self.clicks = []

            def locator(self, selector):
                return _Locator(1)

            def get_by_test_id(self, test_id):
                if test_id.startswith("activity_"):
                    return _HuecoInvisible(1, clicks=self.clicks)
                if test_id == "CalibrationWindow":
                    return _Locator(0)
                return _Locator(1)

        page = _MapaCierreBloqueado()
        espia = _Espia(page, modo="elegir")
        assert _correr(espia) is True
        assert page.clicks == [0]
        assert espia.elegidos == [1, 2, 3]

