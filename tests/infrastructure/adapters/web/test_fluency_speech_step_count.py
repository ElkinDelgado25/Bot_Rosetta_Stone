"""``expected_steps`` no coincide con lo que pinta el reproductor.

Medido en una corrida real: una actividad que la API declaraba de 13 pasos
tenía 10 enunciados. Al acabar el décimo, preguntar por el ``SpeechButton``
(que se queda pintado) devolvía True y el paso 11 esperaba 30 s un
``PromptText`` que ya no existe. La conversación —terminada, y al 100% según
``getProgress``— se daba por fallida y no se persistía.
"""

import asyncio

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Boton:
    """Un localizador de mentira. ``first`` existe porque las respuestas son
    tres: sin él, esperar por ``ChoiceButton`` rompe el modo estricto."""

    def __init__(self, aparece=True):
        self.aparece = aparece
        self.esperas = []
        self.clicks = 0

    @property
    def first(self):
        return self

    async def click(self, **kwargs):
        self.clicks += 1

    async def wait_for(self, state=None, timeout=None):
        self.esperas.append(timeout)
        if not self.aparece:
            raise PlaywrightTimeoutError("no vuelve")

    async def count(self):
        return 1 if self.aparece else 0

    async def is_visible(self):
        return self.aparece

    async def text_content(self):
        if not self.aparece:
            raise PlaywrightTimeoutError(
                'waiting for get_by_test_id("PromptText").first'
            )
        return "Hello"


class _Page:
    def __init__(self, aparece=True, *, prompt=None, speech=None):
        self.boton = _Boton(aparece)
        self.prompt = _Boton(aparece if prompt is None else prompt)
        self.speech = _Boton(aparece if speech is None else speech)
        self.pedidos = []
        self.silencios = []
        self.funciones = []

    def get_by_test_id(self, test_id):
        self.pedidos.append(test_id)
        if test_id == "PromptText":
            return self.prompt
        if test_id == "SpeechButton":
            return self.speech
        if test_id == "CalibrationWindow":
            return _Boton(aparece=False)
        return self.boton

    async def wait_for_function(self, expression, timeout=None, arg=None):
        self.silencios.append(timeout)
        texto = expression or ""
        self.funciones.append(texto)
        if "return 'choice'" in texto:
            if self.boton.aparece:
                return "choice"
            raise PlaywrightTimeoutError("no choice")
        if "PromptText" in texto or "ActivityMapList" in texto:
            if not self.prompt.aparece:
                raise PlaywrightTimeoutError("no prompt")

    async def evaluate(self, expression, arg=None):
        # Sin modal: `_dismiss_microphone_check` sale enseguida.
        return {"presente": False}


def _hay_otro(page, modo="hablar"):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._another_step_starts(10, modo))


class TestStepCount:
    def test_the_prompt_coming_back_means_another_step(self):
        page = _Page(aparece=True)
        assert _hay_otro(page) is True
        assert page.pedidos == ["PromptText"]

    def test_no_prompt_means_the_conversation_ended(self):
        assert _hay_otro(_Page(aparece=False)) is False

    def test_a_lingering_mic_without_a_prompt_means_the_conversation_ended(self):
        """Tras el último enunciado el SpeechButton se queda; PromptText no.

        Preguntar por el micrófono devolvía True y el paso siguiente esperaba
        30 s a PromptText, tumbando una conversación ya hecha (10 pasos, y
        getProgress al 100%).
        """
        page = _Page(speech=True, prompt=False)
        assert _hay_otro(page) is False

    def test_finding_out_does_not_cost_the_long_timeout(self):
        """Hablando, el SpeechButton residual no debe esperar 90 s."""
        page = _Page(aparece=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._another_step_starts(10, "hablar"))
        assert speech.timeout_ms in page.silencios

    def test_a_spoken_next_prompt_waits_until_the_player_or_the_map(self):
        """Correspondence: 15 s tras el silencio seguían cortando en 10/15.

        El PromptText del paso 11 llega después de la línea del NPC, sin
        ``audio_playing``. Hay que esperar al enunciado o a volver al mapa,
        no a una sonda de 15 s.
        """
        page = _Page(aparece=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._another_step_starts(10, "hablar"))
        assert speech.timeout_ms in page.silencios

    def test_waits_for_silence_before_deciding_there_is_no_next_spoken_step(self):
        """Correspondence: 5 s de PromptText mientras el NPC habla era 0%.

        ``_advance_to_next_step`` trata PromptText ausente como avance. Sin
        esperar al silencio, el sondeo de 5 s cae a mitad del audio y se da
        la conversación por acabada en el paso 10 de 15.
        """
        page = _Page(aparece=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._another_step_starts(10, "hablar"))
        assert page.silencios[0] == speech.probe_timeout_ms
        assert speech.timeout_ms in page.silencios

    def test_a_hidden_lesson_map_does_not_end_the_conversation(self):
        """Correspondence: ActivityMapList sigue en el DOM (oculto) entre pasos.

        querySelector lo veía y, con PromptText vacío un instante, se anotaba
        'volvió al mapa' en el paso 10 con percentComplete=0.
        """
        page = _Page(aparece=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._another_step_starts(10, "hablar"))
        guion = " ".join(page.funciones)
        assert "ActivityMapList" in guion
        assert "getClientRects" in guion

    def test_a_covered_lesson_map_is_not_the_end_while_the_player_is_up(self):
        """Correspondence: el mapa sigue con rects detrás del overlay.

        getClientRects no distingue cubierto de visible. En el paso 10 el
        PromptText está vacío un instante, el mapa 'se ve' y se anotaba
        'volvió al mapa' con percentComplete=0. Solo cuenta el mapa si
        elementFromPoint cae dentro de ActivityMapList.
        """
        page = _Page(aparece=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._another_step_starts(10, "hablar"))
        guion = " ".join(f for f in page.funciones if "ActivityMapList" in f)
        assert "elementFromPoint" in guion
        assert "SpeechButton" in guion

    def test_a_stuck_player_is_nudged_forward_after_the_wait_times_out(self):
        """Correspondence: tras el paso 10 el enunciado 11 no aparece solo.

        Advance daba el paso por avanzado (PromptText vacío) y se esperaban
        90 s. getProgress se quedaba en 0. Si SubmitButton sigue, hay que
        pulsarlo y volver a esperar el enunciado.
        """
        page = _Page(aparece=False, prompt=False, speech=True)
        page.submit = _Boton(aparece=True)
        original_by_id = page.get_by_test_id
        esperas_mapa = {"n": 0}

        def _by_id(test_id):
            if test_id == "SubmitButton":
                return page.submit
            return original_by_id(test_id)

        page.get_by_test_id = _by_id  # type: ignore[method-assign]
        original_wait = page.wait_for_function

        async def _wait(expression, timeout=None, arg=None):
            texto = expression or ""
            if "ActivityMapList" in texto:
                esperas_mapa["n"] += 1
                page.funciones.append(texto)
                page.silencios.append(timeout)
                if esperas_mapa["n"] == 1:
                    raise PlaywrightTimeoutError("no prompt yet")
                if page.submit.clicks:
                    page.prompt.aparece = True
                    return "prompt"
                raise PlaywrightTimeoutError("still no")
            return await original_wait(expression, timeout=timeout, arg=arg)

        page.wait_for_function = _wait  # type: ignore[method-assign]
        assert _hay_otro(page) is True
        assert page.submit.clicks == 1

    def test_nudge_does_not_click_omitir(self):
        """El empujón del paso 10 pulsó Omitir y saltó el diálogo entero.

        Tras el timeout el SubmitButton ya decía Omitir (el carrusel de
        vocabulario). Un clic más dejaba la práctica de conversación Omitida
        y getProgress en 0%.
        """
        page = _Page(aparece=False, prompt=False, speech=True)
        page.submit = _Boton(aparece=True)
        original_by_id = page.get_by_test_id
        original_evaluate = page.evaluate

        def _by_id(test_id):
            if test_id == "SubmitButton":
                return page.submit
            return original_by_id(test_id)

        page.get_by_test_id = _by_id  # type: ignore[method-assign]

        async def _evaluate(expression, arg=None):
            texto = expression or ""
            if "SubmitButton" in texto and "data-qa-button-text" in texto:
                return "Omitir"
            return await original_evaluate(expression, arg)

        page.evaluate = _evaluate  # type: ignore[method-assign]
        assert _hay_otro(page) is False
        assert page.submit.clicks == 0


class TestPromptAusente:
    """Red de seguridad: si el sondeo se equivoca, no esperar 30 s.

    El fallo vivo era ``Locator.text_content`` sobre un PromptText que ya no
    está, tragado por el ``except PlaywrightTimeoutError`` de
    ``_complete_activity`` y anotado como actividad fallida.
    """

    def test_missing_prompt_after_the_first_step_is_the_end(self):
        page = _Page(prompt=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        assert asyncio.run(speech._complete_visible_step(11)) is True

    def test_missing_prompt_on_the_first_step_is_still_a_failure(self):
        page = _Page(prompt=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        with pytest.raises(PlaywrightTimeoutError):
            asyncio.run(speech._complete_visible_step(1))

    def test_missing_prompt_after_the_first_choice_step_is_the_end(self):
        page = _Page(prompt=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        assert asyncio.run(speech._complete_visible_choice_step(8)) is True


class TestStepCountEligiendo:
    """Sin micrófono la señal de "queda otro paso" es otra: las respuestas.

    Preguntar por el micrófono en una conversación que se contesta pulsando da
    siempre que no, así que toda actividad ``WithoutReco`` se daba por acabada
    en su primer paso.
    """

    def test_more_choices_mean_another_step(self):
        page = _Page(aparece=True)
        assert _hay_otro(page, modo="elegir") is True
        assert any("ChoiceButton" in f for f in page.funciones)

    def test_no_more_choices_means_the_conversation_ended(self):
        assert _hay_otro(_Page(aparece=False), modo="elegir") is False

    def test_waits_for_silence_before_deciding_there_is_no_next_step(self):
        """Si el enunciado aún suena, 5 s sin ChoiceButton era un falso 100%."""
        page = _Page(aparece=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._another_step_starts(10, "elegir"))
        assert page.silencios[0] == speech.probe_timeout_ms
        assert speech.timeout_ms in page.silencios

    def test_a_chosen_next_step_waits_until_choices_or_the_map(self):
        """Prospective Customer: 5 s sin ChoiceButton cerraba la copia extra en el paso 1."""
        page = _Page(aparece=False)
        speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
        asyncio.run(speech._another_step_starts(1, "elegir"))
        assert speech.timeout_ms in page.silencios

