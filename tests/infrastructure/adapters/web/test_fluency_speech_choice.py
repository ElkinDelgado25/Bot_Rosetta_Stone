"""Marcar la respuesta antes de pedir el micrófono.

De la traza: las respuestas son radios y el micrófono sigue deshabilitado
mientras no haya ninguna marcada (el botón de enviar decía "Omitir"). El clic
al centro de la ficha cae sobre el altavoz, así que hay que insistir por otras
vías y comprobar el resultado en vez de darlo por hecho.
"""

import asyncio

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Texto:
    def __init__(self, cuantos=1):
        self.cuantos = cuantos
        self.clicks = 0

    async def count(self):
        return self.cuantos

    @property
    def first(self):
        return self

    async def click(self, **kwargs):
        self.clicks += 1


class _Choice:
    def __init__(self, texto=None):
        self.texto = texto if texto is not None else _Texto()
        self.box_clicks = 0
        self.dom_clicks = 0
        self.expresiones = []

    def get_by_test_id(self, test_id):
        return self.texto

    async def click(self, **kwargs):
        self.box_clicks += 1

    async def evaluate(self, expression):
        self.dom_clicks += 1
        self.expresiones.append(expression)


class _Page:
    """Se habilita el micrófono tras N intentos de selección."""

    def __init__(self, habilita_tras=1):
        self.habilita_tras = habilita_tras
        self.consultas = 0
        self.evaluated = []
        self.consultado = []

    async def wait_for_function(self, expression, *args, **kwargs):
        self.consultas += 1
        self.consultado.append(expression)
        if self.consultas < self.habilita_tras:
            raise PlaywrightTimeoutError("sigue deshabilitado")

    async def evaluate(self, expression, *args):
        self.evaluated.append(expression)
        return {"existe": True, "html": "<div disabled>", "audio": False}


def _select(page, choice):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._select_choice(choice))


class TestChoiceRegistered:
    def test_it_asks_for_the_three_signals(self):
        """El micrófono no es la única prueba de que se eligió.

        Comprobar solo el micrófono daba por fallida una selección que sí había
        ocurrido, y hacía que la escalera agotara sus cuatro intentos.
        """
        page = _Page(habilita_tras=1)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._choice_registered())
        guion = page.consultado[-1]
        assert "SubmitButton" in guion and "omitir" in guion.lower()
        assert "aria-checked" in guion or "radio" in guion
        assert "SpeechButton" in guion


class TestSelectChoice:
    def test_the_text_is_the_first_target(self):
        choice = _Choice()
        page = _Page(habilita_tras=1)
        assert _select(page, choice) is True
        assert choice.texto.clicks == 1
        assert choice.box_clicks == 0

    def test_falls_back_to_the_whole_card(self):
        choice = _Choice()
        page = _Page(habilita_tras=2)
        assert _select(page, choice) is True
        assert choice.box_clicks == 1

    def test_falls_back_to_a_dom_click(self):
        choice = _Choice()
        page = _Page(habilita_tras=3)
        assert _select(page, choice) is True
        assert choice.dom_clicks == 1

    def test_falls_back_to_a_full_pointer_sequence(self):
        """React escucha pointerdown/mousedown, no siempre el click del DOM."""
        choice = _Choice()
        page = _Page(habilita_tras=4)
        assert _select(page, choice) is True
        assert choice.dom_clicks == 2  # el click simple y la secuencia

    def test_the_pointer_sequence_covers_the_child_too(self):
        choice = _Choice()
        page = _Page(habilita_tras=4)
        _select(page, choice)
        guion = choice.expresiones[-1]
        assert "pointerdown" in guion and "mousedown" in guion
        assert "firstElementChild" in guion

    def test_the_last_resort_walks_the_whole_subtree(self):
        """Sin saber qué nodo escucha, se recorren todos menos el altavoz."""
        choice = _Choice()
        page = _Page(habilita_tras=5)
        assert _select(page, choice) is True
        guion = choice.expresiones[-1]
        assert "querySelectorAll('*')" in guion
        # El altavoz se excluye: pulsarlo reproduce audio en vez de elegir.
        assert "ListenButton" in guion and "esAltavoz" in guion

    def test_gives_up_when_nothing_selects_it(self):
        choice = _Choice()
        page = _Page(habilita_tras=99)
        assert _select(page, choice) is False

    def test_a_choice_without_text_skips_to_the_card(self):
        choice = _Choice(texto=_Texto(cuantos=0))
        page = _Page(habilita_tras=2)
        assert _select(page, choice) is True
        assert choice.box_clicks == 1


class _Listen:
    """El altavoz de una respuesta, con sus tres formas de pulsarlo."""

    def __init__(self, icono=True):
        self.clicks = 0
        self.dom_clicks = 0
        self.icon_clicks = 0
        self.icono = icono

    @property
    def first(self):
        return self

    async def click(self, **kwargs):
        self.clicks += 1

    async def evaluate(self, expression):
        self.dom_clicks += 1

    def get_by_test_id(self, test_id):
        if not self.icono:
            raise RuntimeError("sin icono")
        return _Icono(self)


class _Icono:
    def __init__(self, owner):
        self.owner = owner

    @property
    def first(self):
        return self

    async def click(self, **kwargs):
        self.owner.icon_clicks += 1


def _play(page, listen):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._play_reference_audio(listen))


class TestPlayReferenceAudio:
    def test_the_speaker_click_is_enough_when_it_works(self):
        listen = _Listen()
        assert _play(_Page(habilita_tras=1), listen) is True
        assert listen.clicks == 1
        assert listen.dom_clicks == 0

    def test_falls_back_to_a_dom_click(self):
        # La primera consulta la gasta la espera del reconocedor.
        listen = _Listen()
        assert _play(_Page(habilita_tras=3), listen) is True
        assert listen.dom_clicks == 1

    def test_falls_back_to_the_speaker_icon(self):
        listen = _Listen()
        assert _play(_Page(habilita_tras=4), listen) is True
        assert listen.icon_clicks == 1

    def test_gives_up_when_nothing_plays(self):
        """Antes esto eran 90 s de espera; ahora se rinde y lo dice."""
        assert _play(_Page(habilita_tras=99), _Listen()) is False

    def test_it_tries_a_second_pass(self):
        """La primera pasada puede caer con el reproductor a medio montar."""
        listen = _Listen()
        # 1 espera del reconocedor + 3 vías fallidas + acierta en la 2.ª pasada.
        assert _play(_Page(habilita_tras=6), listen) is True
        assert listen.clicks == 2

    def test_it_waits_for_the_recogniser_first(self):
        page = _Page(habilita_tras=1)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._wait_for_recognizer())
        assert "__rosettaSreReady" in page.consultado[-1]
