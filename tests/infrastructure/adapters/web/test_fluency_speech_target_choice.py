"""La tarjeta que se habla en los pasos de cierre.

El diálogo de Fluency es un árbol: casi todos los pasos aceptan cualquiera de
las tres opciones, pero los de cierre aceptan una sola
(``postProcess.successResponses``). Hablar otra corta la conversación y la
plataforma marca la actividad como omitida (``percentComplete`` 0 con los pasos
previos bien contestados). Estas pruebas cubren la elección sin navegador.
"""

import asyncio
import logging

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
    _opcion_objetivo,
)


def _paso(opciones, success_ids):
    return {
        "id": "step-x",
        "success_ids": list(success_ids),
        "options": [
            {"id": i, "text": t, "sha": s} for i, t, s in opciones
        ],
    }


_FREE = _paso(
    [
        ("opt-a", "Yes, of course.", "aaa"),
        ("opt-b", "No, sorry.", "bbb"),
        ("opt-c", "Maybe.", "ccc"),
    ],
    ["opt-a", "opt-b", "opt-c"],
)

_TAIL = _paso(
    [
        ("opt-d", "Only one.", "ddd"),
        ("opt-e", "Two.", "eee"),
        ("opt-f", "No, I always write the same old things.", "fff"),
    ],
    ["opt-f"],
)


class TestOpcionObjetivo:
    def test_free_step_returns_none(self):
        visibles = ["Yes, of course.", "No, sorry.", "Maybe."]
        assert _opcion_objetivo(visibles, [_FREE]) is None

    def test_restricted_step_picks_accepted_card(self):
        visibles = ["Only one.", "No, I always write the same old things.", "Two."]
        objetivo = _opcion_objetivo(visibles, [_TAIL])
        assert objetivo is not None
        assert objetivo["indice"] == 1
        assert objetivo["id"] == "opt-f"
        assert objetivo["sha"] == "fff"

    def test_normalizes_case_and_whitespace(self):
        visibles = ["  NO,   I always write the SAME old things. "]
        objetivo = _opcion_objetivo(visibles, [_TAIL])
        assert objetivo is not None
        assert objetivo["indice"] == 0

    def test_unknown_prompt_returns_none(self):
        assert _opcion_objetivo(["Totally different sentence."], [_TAIL]) is None

    def test_empty_inputs_return_none(self):
        assert _opcion_objetivo([], [_TAIL]) is None
        assert _opcion_objetivo(["x"], []) is None

    def test_intersection_across_candidates(self):
        """El mismo trío puede casar con un paso libre y uno de cierre."""
        visibles = ["Yes, of course.", "No, sorry.", "Maybe."]
        cierre = _paso(
            [
                ("opt-a", "Yes, of course.", "aaa"),
                ("opt-b", "No, sorry.", "bbb"),
                ("opt-c", "Maybe.", "ccc"),
            ],
            ["opt-b"],
        )
        objetivo = _opcion_objetivo(visibles, [_FREE, cierre])
        assert objetivo is not None
        assert objetivo["indice"] == 1
        assert objetivo["id"] == "opt-b"

    def test_conflicting_candidates_return_none(self):
        uno = _paso(
            [
                ("opt-a", "Yes, of course.", "aaa"),
                ("opt-b", "No, sorry.", "bbb"),
                ("opt-c", "Maybe.", "ccc"),
            ],
            ["opt-a"],
        )
        otro = _paso(
            [
                ("opt-a", "Yes, of course.", "aaa"),
                ("opt-b", "No, sorry.", "bbb"),
                ("opt-c", "Maybe.", "ccc"),
            ],
            ["opt-c"],
        )
        visibles = ["Yes, of course.", "No, sorry.", "Maybe."]
        assert _opcion_objetivo(visibles, [uno, otro]) is None

    def test_accepted_option_not_visible_returns_sha_only(self):
        """Si la tarjeta aceptada no está entre las visibles, queda el sha."""
        cuarto = _paso(
            [
                ("opt-a", "Yes, of course.", "aaa"),
                ("opt-b", "No, sorry.", "bbb"),
                ("opt-c", "Maybe.", "ccc"),
                ("opt-x", "Detrás de ti.", "xxx"),
            ],
            ["opt-x"],
        )
        visibles = ["Yes, of course.", "No, sorry.", "Maybe."]
        objetivo = _opcion_objetivo(visibles, [cuarto])
        assert objetivo is not None
        assert objetivo["indice"] is None
        assert objetivo["id"] == "opt-x"
        assert objetivo["sha"] == "xxx"


class _Texto:
    def __init__(self, texto):
        self.texto = texto

    async def count(self):
        return 1

    async def text_content(self):
        return self.texto

    @property
    def first(self):
        return self


class _Tarjeta:
    def __init__(self, texto):
        self.texto = texto

    def get_by_test_id(self, test_id):
        assert test_id == "ChoiceText"
        return _Texto(self.texto)


class _Choices:
    def __init__(self, textos):
        self.cards = [_Tarjeta(t) for t in textos]

    @property
    def first(self):
        return self.cards[0]

    async def count(self):
        return len(self.cards)

    def nth(self, indice):
        return self.cards[indice]


class _Page:
    pass


def _speech_con(pasos):
    speech = PlaywrightFluencySpeechPage(_Page())  # type: ignore[arg-type]
    speech._pasos_secuencia = pasos
    speech._logger = logging.getLogger("test")
    return speech


class TestTarjetaAHablar:
    def test_picks_accepted_card_in_restricted_step(self):
        speech = _speech_con([_TAIL])
        choices = _Choices(
            ["Only one.", "Two.", "No, I always write the same old things."]
        )
        elegido = asyncio.run(speech._tarjeta_a_hablar(choices))
        assert elegido is choices.cards[2]

    def test_free_step_keeps_first_card(self):
        speech = _speech_con([_FREE])
        choices = _Choices(["Yes, of course.", "No, sorry.", "Maybe."])
        elegido = asyncio.run(speech._tarjeta_a_hablar(choices))
        assert elegido is choices.cards[0]

    def test_no_steps_keeps_first_card(self):
        speech = _speech_con([])
        choices = _Choices(["Only one.", "Two.", "No, I always write the same old things."])
        elegido = asyncio.run(speech._tarjeta_a_hablar(choices))
        assert elegido is choices.cards[0]
