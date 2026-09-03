"""Tests for the Stories hour-reporting flow.

The rules that matter: entering a story comes first (without it there is no
server-side session to credit), the player's own usage session wins over an
invented one, and a rejected chunk stops the run without undoing what was
already credited.
"""

import asyncio

from Resolucion_script_rosseta.aplicacion.orchestrators.stories_orchestrator import (
    StoriesOrchestrator,
)
from Resolucion_script_rosseta.aplicacion.services.stories_session_capturer import (
    StoriesSessionCapturer,
)
from Resolucion_script_rosseta.aplicacion.services.stories_usage_planner import (
    StoriesUsagePlanner,
)


class _Page:
    def __init__(self, story="Cats"):
        self.story = story
        self.opened = False

    async def open_stories(self):
        self.opened = True

    async def enter_first_story(self):
        return self.story


class _Api:
    def __init__(self, fail_after=None, can_start=True):
        self.can_start = can_start
        self.fail_after = fail_after
        self.started = []
        self.reported = []

    async def start_usage_session(self, session_id, language, started_ago_seconds):
        self.started.append((session_id, language, started_ago_seconds))
        return self.can_start

    async def report_usage(self, session_id, seconds):
        if self.fail_after is not None and len(self.reported) >= self.fail_after:
            return False
        self.reported.append((session_id, seconds))
        return True


class _Monitor:
    def __init__(self):
        self.added = []
        self.removed = []

    def add_request_listener(self, listener):
        self.added.append(listener)

    def remove_request_listener(self, listener):
        self.removed.append(listener)


async def _no_sleep(_seconds):
    return None


def _orchestrator(page=None, api=None, capturer=None, monitor=None, chunk=600):
    return StoriesOrchestrator(
        stories_page=page or _Page(),
        stories_api=api or _Api(),
        planner=StoriesUsagePlanner(chunk_min_sec=chunk, chunk_max_sec=chunk),
        session_capturer=capturer,
        network_monitor=monitor,
        sleep=_no_sleep,
        id_factory=lambda: "propia-1",
    )


class TestStoriesOrchestrator:
    def test_credits_the_whole_budget_in_chunks(self):
        api = _Api()
        result = asyncio.run(_orchestrator(api=api).execute(0.5))  # 1800 s
        assert [seconds for _, seconds in api.reported] == [600, 600, 600]
        assert result.seconds_credited == 1800
        assert result.hours_credited == 0.5
        assert result.chunks_sent == 3
        assert result.failed is False

    def test_opens_its_own_session_declaring_the_first_chunk_as_elapsed(self):
        api = _Api()
        asyncio.run(_orchestrator(api=api).execute(0.5))
        assert api.started == [("propia-1", "ENG", 600)]

    def test_reuses_the_players_session_instead_of_opening_one(self):
        api = _Api()
        capturer = StoriesSessionCapturer()
        capturer.session_identifier = "js-99"
        result = asyncio.run(_orchestrator(api=api, capturer=capturer).execute(0.5))
        assert api.started == []
        assert {session for session, _ in api.reported} == {"js-99"}
        assert result.failed is False

    def test_without_a_story_nothing_is_reported(self):
        api = _Api()
        result = asyncio.run(_orchestrator(page=_Page(story=None), api=api).execute(1))
        assert result.failed is True
        assert api.started == [] and api.reported == []

    def test_a_refused_session_aborts_before_reporting(self):
        api = _Api(can_start=False)
        result = asyncio.run(_orchestrator(api=api).execute(1))
        assert result.failed is True
        assert api.reported == []

    def test_a_rejected_chunk_keeps_what_was_already_credited(self):
        api = _Api(fail_after=2)
        result = asyncio.run(_orchestrator(api=api).execute(0.5))
        assert result.seconds_credited == 1200
        assert result.chunks_sent == 2
        assert result.failed is True
        assert result.error

    def test_an_empty_budget_does_not_touch_the_browser(self):
        page = _Page()
        result = asyncio.run(_orchestrator(page=page).execute(0))
        assert page.opened is False
        assert result.chunks_sent == 0
        assert result.failed is False

    def test_listens_to_the_player_only_while_entering_the_story(self):
        monitor = _Monitor()
        asyncio.run(_orchestrator(monitor=monitor).execute(0.2))
        assert len(monitor.added) == 1
        assert len(monitor.removed) == 1

    def test_the_listener_is_removed_even_if_entering_fails(self):
        class _Broken(_Page):
            async def enter_first_story(self):
                raise RuntimeError("la SPA no pintó nada")

        monitor = _Monitor()
        orch = _orchestrator(page=_Broken(), monitor=monitor)
        try:
            asyncio.run(orch.execute(0.2))
        except RuntimeError:
            pass
        assert len(monitor.removed) == 1

