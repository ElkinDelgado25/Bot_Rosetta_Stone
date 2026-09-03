"""Which activity types go through the browser instead of the API.

Las dos conversaciones, que son las únicas ``ordering: "tree"`` del catálogo y
las únicas que la API deja en ``percentComplete=0`` por mucho que se le mande el
mensaje correcto. Lo que el servidor no acredita fabricado es el árbol, no la
voz: por eso ``WithoutReco``, que se contesta pulsando y no hablando, también va
por aquí.
"""

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    BROWSER_COMPLETED_TYPES,
    CompleteFluencyOrchestrator,
)


def _orchestrator(**kwargs):
    return CompleteFluencyOrchestrator(api_port=object(), **kwargs)


class TestBrowserCompletedTypes:
    def test_both_tree_conversations_are_routed_there(self):
        """Las dos, con micrófono y sin él: lo que la API no acredita es el árbol."""
        assert BROWSER_COMPLETED_TYPES == (
            "DialogueExpressionWithReco",
            "DialogueExpressionWithoutReco",
        )

    def test_the_default_set_is_used_when_none_is_given(self):
        assert _orchestrator().browser_completed_types == BROWSER_COMPLETED_TYPES

    def test_extra_types_can_be_added_to_try_them_out(self):
        orch = _orchestrator(
            browser_completed_types=BROWSER_COMPLETED_TYPES + ("PronunciationPhoneme",)
        )
        assert "PronunciationPhoneme" in orch.browser_completed_types

    def test_an_empty_set_sends_everything_through_the_api(self):
        assert _orchestrator(browser_completed_types=()).browser_completed_types == ()

