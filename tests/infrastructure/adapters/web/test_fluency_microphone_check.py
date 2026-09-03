"""El modal de "Comprobación de micrófono".

Lo que en realidad bloqueaba las actividades de conversación: una capa por
encima de todo (``position: fixed``, ``z-index: 7000``). Detrás de ella ningún
clic llegaba a las respuestas y el micrófono seguía deshabilitado; durante once
corridas pareció un problema de selectores, hasta que un fotograma de la traza
lo enseñó.

Tiene **dos caras** y solo la primera tiene botón: elegir dispositivo y pulsar
*Comenzar*, y después "Comprobando el micrófono...", que se queda escuchando
sin nada que pulsar. Buscar el botón en la segunda decía "no se encontró el
modal" mientras seguía tapando la pantalla, así que lo que se mira es la
ventana (``CalibrationWindow``) y lo que se espera es que se vaya.
"""

import asyncio

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page import (
    fluency_speech_page as modulo,
)
from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


ESCUCHANDO = {
    "presente": True,
    "escuchando": True,
    "barras": 10,
    "encendidas": 1,
    "senal": True,
    "texto": "Comprobando el micrófono...",
}
SIN_MODAL = {"presente": False}


class _Opciones:
    def __init__(self, cuantas):
        self.cuantas = cuantas

    async def count(self):
        return self.cuantas


class _Selector:
    def __init__(self, cuantos=1, opciones=2):
        self.cuantos = cuantos
        self.opciones = opciones
        self.elegido = None

    async def count(self):
        return self.cuantos

    @property
    def first(self):
        return self

    def locator(self, css):
        return _Opciones(self.opciones)

    async def select_option(self, index=None):
        self.elegido = index


class _Boton:
    def __init__(self, cuantos=1, falla=False):
        self.cuantos = cuantos
        self.falla = falla
        self.pulsado = False

    async def count(self):
        return self.cuantos

    @property
    def first(self):
        return self

    async def click(self, **kwargs):
        if self.falla:
            raise RuntimeError("no se puede pulsar")
        self.pulsado = True


class _Page:
    """El reproductor: el botón puede estar en cualquiera de las tres vías.

    *calibracion* es lo que devuelve ``__rosettaMicCheckState`` (``None`` si el
    guion no llegó a instalarse) y *se_cierra* dice si la ventana acaba
    yéndose, que es la única señal de que la comprobación pasó.
    """

    def __init__(
        self,
        boton=None,
        selector=None,
        donde="por rol",
        vigilante=False,
        calibracion=ESCUCHANDO,
        se_cierra=False,
    ):
        self.boton = boton if boton is not None else _Boton()
        self.vacio = _Boton(cuantos=0)
        self.selector = selector if selector is not None else _Selector()
        self.donde = donde
        self.vigilante = vigilante
        self.calibracion = calibracion
        self.se_cierra = se_cierra
        self.rol_pedido = None
        self.despedidas = 0
        self.esperas = 0

    async def evaluate(self, expression, *args):
        if "__rosettaMicCheckState" in expression:
            return self.calibracion
        if "__rosettaDismissMicCheck" in expression:
            self.despedidas += 1
            return self.vigilante
        return self.vigilante

    async def wait_for_function(self, expression, *args, **kwargs):
        self.esperas += 1
        if not self.se_cierra:
            raise modulo.PlaywrightTimeoutError("la ventana sigue ahí")

    async def screenshot(self, path=None):
        return None

    def get_by_role(self, role, name=None):
        self.rol_pedido = (role, name)
        return self.boton if self.donde == "por rol" else self.vacio

    def get_by_test_id(self, test_id):
        return self.boton if self.donde == "por data-qa" else self.vacio

    def get_by_text(self, patron):
        return self.boton if self.donde == "por texto" else self.vacio

    def locator(self, css):
        return self.selector


def _dismiss(page):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._dismiss_microphone_check())


class TestMicrophoneCheck:
    def test_without_the_modal_it_does_nothing(self):
        """Sin ventana no hay nada que cerrar, y decirlo ahorra los intentos.

        Antes se pulsaba a ciegas en cada paso y se registraba "no se encontró
        el botón del modal" aunque no hubiera modal ninguno.
        """
        page = _Page(calibracion=SIN_MODAL)
        _dismiss(page)
        assert page.boton.pulsado is False
        assert page.esperas == 0

    def test_the_watcher_gets_the_first_word(self):
        """Si el vigilante lo cierra y la ventana se va, no se toca nada más."""
        page = _Page(se_cierra=True)
        _dismiss(page)
        assert page.boton.pulsado is False
        assert page.selector.elegido is None

    def test_it_waits_for_the_window_to_go(self):
        """Que el botón se pulse no es que la comprobación haya pasado.

        La ventana se queda escuchando después, y mientras está tapa las
        respuestas: seguir adelante solo gastaba los cinco intentos de marcar
        una respuesta contra el modal.
        """
        page = _Page(se_cierra=True)
        _dismiss(page)
        assert page.esperas == 1

    def test_if_the_window_stays_it_falls_back_to_pressing(self):
        page = _Page(se_cierra=False)
        _dismiss(page)
        assert page.boton.pulsado is True

    def test_picks_a_device_and_starts(self):
        page = _Page()
        _dismiss(page)
        assert page.selector.elegido == 1  # la última opción disponible
        assert page.boton.pulsado is True

    def test_it_finds_the_button_by_data_qa(self):
        """*Comenzar* no es un <button>: buscarlo por rol no encuentra nada.

        Ese detalle dejó el modal abierto en silencio una corrida entera.
        """
        page = _Page(donde="por data-qa")
        _dismiss(page)
        assert page.boton.pulsado is True

    def test_it_finds_the_button_by_text(self):
        page = _Page(donde="por texto")
        _dismiss(page)
        assert page.boton.pulsado is True

    def test_the_device_is_chosen_before_pressing(self):
        # El botón puede depender de que haya dispositivo seleccionado.
        page = _Page(donde="por data-qa")
        _dismiss(page)
        assert page.selector.elegido == 1

    def test_a_dropdown_without_options_does_not_stop_it(self):
        page = _Page(selector=_Selector(opciones=0))
        _dismiss(page)
        assert page.selector.elegido is None
        assert page.boton.pulsado is True

    def test_a_button_that_refuses_never_sinks_the_run(self):
        page = _Page(boton=_Boton(falla=True))
        _dismiss(page)  # no lanza

    def test_a_dropdown_that_refuses_still_lets_the_button_be_pressed(self):
        """Elegir dispositivo es un extra; pulsar *Comenzar* es lo que importa.

        Con todo en el mismo try, un fallo del desplegable saltaba al except y
        el modal se quedaba abierto sin una sola línea que lo explicara.
        """

        class _SelectorRoto(_Selector):
            async def select_option(self, index=None):
                raise RuntimeError("no interactuable")

        page = _Page(selector=_SelectorRoto())
        _dismiss(page)
        assert page.boton.pulsado is True

    def test_it_looks_for_the_spanish_and_english_labels(self):
        page = _Page()
        _dismiss(page)
        patron = page.rol_pedido[1].pattern
        assert "comenzar" in patron and "start" in patron

    def test_it_reports_whether_there_was_a_check(self):
        """El que llama lo necesita: la comprobación se come la pulsación del
        micrófono, y hay que volver a pulsarlo solo si de verdad apareció."""
        assert _dismiss(_Page(calibracion=SIN_MODAL)) is False
        assert _dismiss(_Page(se_cierra=True)) is True

    def test_without_the_script_it_never_claims_there_was_one(self):
        """Sin saberlo, decir que sí haría pulsar el micrófono dos veces.

        Y la segunda pulsación lo apaga.
        """
        assert _dismiss(_Page(calibracion=None)) is False

    def test_without_the_script_it_still_tries(self):
        """Si el guion no se instaló, ``__rosettaMicCheckState`` no existe.

        Ahí no se sabe si hay modal, así que se intenta igual: es el camino que
        había antes de saber mirar la ventana.
        """
        page = _Page(calibracion=None)
        _dismiss(page)
        assert page.boton.pulsado is True


class TestAutoDismissWatcher:
    def test_a_watcher_closes_the_modal_whenever_it_appears(self):
        """El modal no está al abrir la actividad: aparece un momento después.

        En la traza sale en 1 de 110 instantáneas, así que mirar una vez —o
        incluso una vez por paso— se lo pierde. El vigilante inyectado no
        depende del momento.
        """
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "MutationObserver" in guion
        assert "__rosettaDismissMicCheck" in guion

    def test_it_only_matches_the_start_button(self):
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "comenzar|start" in guion
        # Solo nodos hoja: si no, el clic cae en un contenedor cualquiera.
        assert "nodo.children.length" in guion

    def test_it_dispatches_a_pointer_sequence(self):
        # React no siempre reacciona a un click() a secas.
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "pointerdown" in guion and "mousedown" in guion

    def test_it_also_presses_retry(self):
        """La comprobación falla la primera vez y ofrece "Volver a intentar"."""
        assert "volver a intentar" in modulo._VIRTUAL_MIC_SCRIPT

    def test_it_presses_continue_on_the_success_dialog(self):
        """Hay una tercera cara: "Comprobación de micrófono exitosa".

        Sale con un *Continuar* y se queda ahí tapando la actividad aunque la
        comprobación haya ido bien: el botón de enviar seguía diciendo "Omitir"
        hasta agotar los 90 s.
        """
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "continuar|continue" in guion

    def test_continue_is_only_pressed_inside_the_window(self):
        """"Continuar" sale en media plataforma; fuera de la ventana no se toca."""
        guion = modulo._VIRTUAL_MIC_SCRIPT
        dentro = guion.index("continuar|continue")
        etiquetas = guion.index("const etiquetas = ventana")
        assert etiquetas < dentro
        # La rama sin ventana no lo lleva.
        sin_ventana = guion.index(
            ": /^(comenzar|start|volver a intentar|try again|retry)$/i;"
        )
        assert sin_ventana > dentro

    def test_it_recognises_the_window_by_data_qa(self):
        """La segunda cara del modal no tiene botón: se la reconoce por la
        ventana, no por lo que se pueda pulsar dentro."""
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "CalibrationWindow" in guion
        assert "__rosettaMicCheckState" in guion


class TestMicrophoneSignal:
    """Un micrófono virtual sin nada inyectado es silencio.

    La comprobación pide decir "1, 2, 3, 4, 5" y responde "No se detectó su
    entrada de audio" — se vio en el fotograma de la corrida 19.
    """

    def test_there_is_a_continuous_signal_for_the_check(self):
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "__rosettaStartMicNoise" in guion
        assert "createOscillator" in guion

    def test_the_signal_goes_to_a_bus_that_outlives_the_destination(self):
        """El destino se crea en cada ``getUserMedia``, la señal no.

        Conectando al destino de turno, lo que empezara a sonar antes de que la
        página pidiera el micrófono acababa conectado a nada: el medidor de la
        comprobación se quedaba en una barra de diez y la ventana no se iba.
        """
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "connect(state.bus)" in guion
        assert "state.bus.connect(state.destination)" in guion
        assert "connect(state.destination)" not in guion.replace(
            "state.bus.connect(state.destination)", ""
        )

    def test_the_signal_can_start_before_the_page_asks_for_the_mic(self):
        # asegurarContexto() crea contexto y bus sin esperar a getUserMedia.
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "asegurarContexto" in guion

    def test_the_signal_starts_before_pressing(self):
        guion = modulo._VIRTUAL_MIC_SCRIPT
        inicio = guion.index("__rosettaStartMicNoise();")
        clic = guion.index("emitirClic(objetivo);")
        assert inicio < clic

    def test_the_signal_stops_when_the_window_goes(self):
        """Un zumbido permanente estorbaría al reconocedor después.

        Lo decidía un temporizador de 30 s, que tanto podía cortar a mitad de
        la comprobación como seguir sonando encima de la respuesta. Ahora la
        para el observador cuando la ventana se va, no un temporizador largo.
        (El único ``setTimeout`` que queda es el throttle de 250 ms del propio
        observador, no un reloj que decida cuándo callar la señal.)
        """
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "__rosettaStopMicNoise" in guion
        # La señal se corta desde atenderCalibracion (observador), no por un
        # temporizador de segundos.
        assert "30_000" not in guion and "30000" not in guion
        # El único timer es el throttle corto del observador.
        assert "250 - (Date.now()" in guion

    def test_feeding_an_answer_silences_the_check_loop(self):
        """Si el bucle del "1, 2, 3, 4, 5" sigue, el reconocedor oye las dos."""
        guion = modulo._VIRTUAL_MIC_SCRIPT
        alimentar = guion.index("__rosettaFeedMicrophone")
        parada = guion.index("__rosettaStopMicNoise();", alimentar)
        assert parada > alimentar


class TestFakeAudioDevice:
    def test_the_virtual_microphone_announces_itself(self):
        """En un contenedor no hay micrófonos: el modal se queda vacío."""
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "enumerateDevices" in guion
        assert "audioinput" in guion
