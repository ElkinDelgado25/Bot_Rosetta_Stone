"""Which activity types go through the browser instead of the API.

Only the ones with a microphone belong here. Routing a type without one costs
90 s of waiting per activity and completes nothing — measured, not guessed.
"""

from rosseta_stone_script_a.application.orchestrators.complete_fluency_orchestrator import (
    BROWSER_COMPLETED_TYPES,
    CompleteFluencyOrchestrator,
)


def _orchestrator(**kwargs):
    return CompleteFluencyOrchestrator(api_port=object(), **kwargs)


class TestBrowserCompletedTypes:
    def test_only_the_type_with_a_microphone_is_routed_there(self):
        """"WithoutReco" no tiene micrófono: mandarlo aquí fue un error medido."""
        assert BROWSER_COMPLETED_TYPES == ("DialogueExpressionWithReco",)

    def test_the_default_set_is_used_when_none_is_given(self):
        assert _orchestrator().browser_completed_types == BROWSER_COMPLETED_TYPES

    def test_extra_types_can_be_added_to_try_them_out(self):
        orch = _orchestrator(
            browser_completed_types=BROWSER_COMPLETED_TYPES + ("PronunciationPhoneme",)
        )
        assert "PronunciationPhoneme" in orch.browser_completed_types

    def test_an_empty_set_sends_everything_through_the_api(self):
        assert _orchestrator(browser_completed_types=()).browser_completed_types == ()
