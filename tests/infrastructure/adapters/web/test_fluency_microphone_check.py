"""El modal de "Comprobación de micrófono".

Lo que en realidad bloqueaba las actividades de conversación: una capa por
encima de todo, con un desplegable de dispositivos y un botón *Comenzar*.
Detrás de ella ningún clic llegaba a las respuestas y el micrófono seguía
deshabilitado; durante once corridas pareció un problema de selectores, hasta
que un fotograma de la traza lo enseñó.
"""

import asyncio

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page import (
    fluency_speech_page as modulo,
)
from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


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
    """El reproductor: el botón puede estar en cualquiera de las tres vías."""

    def __init__(self, boton=None, selector=None, donde="por rol", vigilante=False):
        self.boton = boton if boton is not None else _Boton()
        self.vacio = _Boton(cuantos=0)
        self.selector = selector if selector is not None else _Selector()
        self.donde = donde
        self.vigilante = vigilante
        self.rol_pedido = None

    async def evaluate(self, expression, *args):
        # El vigilante inyectado: dice si él mismo ya cerró el modal.
        return self.vigilante

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
    asyncio.run(speech._dismiss_microphone_check())


class TestMicrophoneCheck:
    def test_picks_a_device_and_starts(self):
        page = _Page()
        _dismiss(page)
        assert page.selector.elegido == 1  # la última opción disponible
        assert page.boton.pulsado is True

    def test_without_the_modal_it_does_nothing(self):
        page = _Page(boton=_Boton(cuantos=0))
        _dismiss(page)
        assert page.boton.pulsado is False

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

    def test_the_watcher_gets_the_first_word(self):
        """Si el vigilante ya lo cerró, no se toca nada más."""
        page = _Page(vigilante=True)
        _dismiss(page)
        assert page.boton.pulsado is False

    def test_it_looks_for_the_spanish_and_english_labels(self):
        page = _Page()
        _dismiss(page)
        patron = page.rol_pedido[1].pattern
        assert "comenzar" in patron and "start" in patron


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


class TestMicrophoneSignal:
    """Un micrófono virtual sin nada inyectado es silencio.

    La comprobación pide decir "1, 2, 3, 4, 5" y responde "No se detectó su
    entrada de audio" — se vio en el fotograma de la corrida 19.
    """

    def test_there_is_a_continuous_signal_for_the_check(self):
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "__rosettaStartMicNoise" in guion
        assert "createOscillator" in guion
        # Conectada al mismo destino que hace de micrófono.
        assert "connect(state.destination)" in guion

    def test_the_signal_starts_before_pressing(self):
        guion = modulo._VIRTUAL_MIC_SCRIPT
        inicio = guion.index("__rosettaStartMicNoise();")
        clic = guion.index("emitirClic(objetivo);")
        assert inicio < clic

    def test_the_signal_does_not_stay_forever(self):
        # Un zumbido permanente estorbaría al reconocedor después.
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "__rosettaStopMicNoise" in guion
        assert "setTimeout" in guion


class TestFakeAudioDevice:
    def test_the_virtual_microphone_announces_itself(self):
        """En un contenedor no hay micrófonos: el modal se queda vacío."""
        guion = modulo._VIRTUAL_MIC_SCRIPT
        assert "enumerateDevices" in guion
        assert "audioinput" in guion
