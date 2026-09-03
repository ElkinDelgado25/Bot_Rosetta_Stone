"""Tracing the speech flow: keep the failures, drop the successes.

A trace is the only way to see what the player was doing when the run happens
headless inside a container. It also weighs megabytes, and a run touches dozens
of activities — so only the ones worth looking at are kept.
"""

import asyncio
from pathlib import Path

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Tracing:
    def __init__(self):
        self.started = False
        self.stopped_to = "no parada"

    async def start(self, **kwargs):
        self.started = True

    async def stop(self, path=None):
        self.stopped_to = path


class _Page:
    def __init__(self):
        self.context = type("Ctx", (), {"tracing": _Tracing()})()


def _page_with(result, tmp_path=None):
    page = _Page()
    speech = PlaywrightFluencySpeechPage(page, trace_dir=tmp_path)  # type: ignore[arg-type]

    async def _fake(**kwargs):
        if isinstance(result, Exception):
            raise result
        return result

    speech._complete_activity = _fake
    return page, speech


def _run(speech):
    return asyncio.run(
        speech.complete_activity(
            course_title="C", lesson_title="L", activity_id="abcdef123456", expected_steps=1
        )
    )


class TestSpeechTracing:
    def test_a_failed_activity_leaves_a_trace(self, tmp_path):
        page, speech = _page_with(False, tmp_path)
        assert _run(speech) is False
        saved = page.context.tracing.stopped_to
        assert saved and Path(saved).name == "speech_trace_abcdef12.zip"

    def test_a_successful_activity_leaves_nothing(self, tmp_path):
        page, speech = _page_with(True, tmp_path)
        assert _run(speech) is True
        assert page.context.tracing.stopped_to is None

    def test_without_a_trace_dir_nothing_is_recorded(self, tmp_path):
        page, speech = _page_with(False, None)
        assert _run(speech) is False
        assert page.context.tracing.started is False

    def test_an_exception_still_saves_the_trace(self, tmp_path):
        page, speech = _page_with(RuntimeError("boom"), tmp_path)
        try:
            _run(speech)
        except RuntimeError:
            pass
        assert page.context.tracing.stopped_to

