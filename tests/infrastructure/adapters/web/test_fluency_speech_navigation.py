"""Opening the lesson before the speech flow can start.

This covers the navigation half of the conversation workflow, which is where a
missing ``await`` turned every single speech attempt into
``'coroutine' object has no attribute 'get_by_test_id'`` — 26 activities lost
in one run without the flow ever reaching the microphone.
"""

import asyncio

import pytest

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)


class _Element:

    def __init__(self, name):
        self.name = name
        self.clicks = []


    @property
    def first(self):
        """Un locator de verdad siempre lo ofrece; el código lo usa."""
        return self
    def get_by_test_id(self, test_id):
        return _Button(self, test_id)

    async def wait_for(self, state=None, timeout=None):
        return None


class _Button:

    def __init__(self, owner, test_id):
        self.owner = owner
        self.test_id = test_id


    @property
    def first(self):
        """Un locator de verdad siempre lo ofrece; el código lo usa."""
        return self
    async def click(self, **kwargs):
        self.owner.clicks.append(self.test_id)


class _Cards:
    """Una lista de tarjetas que sabe filtrarse por texto, como un Locator."""


    def __init__(self, titles):
        self.titles = titles
        self.matched = None
        self.first = _Element(titles[0] if titles else None)

    def filter(self, has_text=None):
        found = _Cards([t for t in self.titles if has_text in t])
        self.matched = found
        return found

    async def count(self):
        return len(self.titles)


class _Page:
    def __init__(self, courses, lessons):
        self.by_test_id = {
            "CourseDisplayerDiv": _Cards(courses),
            "LessonDisplayer": _Cards(lessons),
            "ActivityMapList": _Element("map"),
        }
        self.visited = []

    async def goto(self, url):
        self.visited.append(url)

    def get_by_test_id(self, test_id):
        return self.by_test_id.setdefault(test_id, _Element(test_id))


def _open(courses, lessons, course="Business (B1)", lesson="Registration"):
    page = _Page(courses, lessons)
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    asyncio.run(speech._open_lesson(course, lesson))
    return page


class TestOpenLesson:
    def test_launches_the_course_and_the_lesson(self):
        page = _open(["Business (B1)"], ["Registration"])
        assert page.visited == ["https://learn.rosettastone.com"]
        assert page.by_test_id["CourseDisplayerDiv"].matched.first.clicks == [
            "LaunchCourseButton"
        ]
        assert page.by_test_id["LessonDisplayer"].matched.first.clicks == [
            "LaunchButton"
        ]

    def test_a_repeated_lesson_title_opens_the_first_one(self):
        """"Registration" existe en varios cursos: antes esto abortaba."""
        page = _open(["Business (B1)"], ["Registration", "Registration II"])
        assert page.by_test_id["LessonDisplayer"].matched.first.clicks == [
            "LaunchButton"
        ]

    def test_a_lesson_that_is_not_there_is_an_error(self):
        with pytest.raises(RuntimeError, match="lección"):
            _open(["Business (B1)"], ["Otra cosa"])

    def test_a_course_that_is_not_there_is_an_error(self):
        with pytest.raises(RuntimeError, match="curso"):
            _open(["Otro curso"], ["Registration"])
