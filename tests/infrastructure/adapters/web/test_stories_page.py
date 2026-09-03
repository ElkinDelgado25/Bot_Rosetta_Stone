"""Tests for the Stories listing page.

The listing has rendered in more than one shape, and "no tiles" is the same
symptom for three different causes (the account has no Stories, the session
arrived logged out, the markup changed). The adapter has to try every known
shape and, when it still finds nothing, say where it ended up.
"""

import asyncio
from types import SimpleNamespace

import Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.stories_page as stories_module
from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page.stories_page import (
    StoriesPage,
)


class _Locator:
    def __init__(self, count=0, text="Cats"):
        self._count = count
        self._text = text
        self.first = self

    async def count(self):
        return self._count

    async def inner_text(self):
        return self._text


class _Interactor:
    """Devuelve fichas solo para los selectores que se le digan."""

    def __init__(self, matching_css=(), text=" Cats ", labels=(), click_first_raises=None):
        self.matching_css = set(matching_css)
        self.text = text
        self.labels = set(labels)
        self.click_first_raises = click_first_raises
        self.clicked = []
        self.clicked_first = []
        self.asked = []

    async def find(self, selector):
        css = getattr(selector, "value", str(selector))
        self.asked.append(css)
        return _Locator(count=1 if css in self.matching_css else 0, text=self.text)

    async def exists(self, selector, timeout=None):
        return getattr(selector, "value", None) in self.labels

    async def click(self, target):
        self.clicked.append(target)

    async def click_first(self, target):
        self.clicked_first.append(getattr(target, "value", target))
        if self.click_first_raises:
            raise self.click_first_raises


class _Navigator:
    def __init__(self, title="Rosetta Stone"):
        self.visited = []
        self._title = title

    async def go_to(self, url, wait_for_load=False):
        self.visited.append(url)

    async def get_title(self):
        return self._title


class _Dumper:
    def __init__(self):
        self.meta = []
        self.screenshots = []

    async def dump_meta(self, tag, meta):
        self.meta.append((tag, meta))

    async def dump_screenshot(self, tag):
        self.screenshots.append(tag)


def _page(interactor, navigator=None, dumper=None):
    session = SimpleNamespace(
        interactor=interactor,
        navigator=navigator or _Navigator(),
        debug_dumper=dumper,
    )
    return StoriesPage(web_session=session)


class TestStoriesPage:
    def test_opens_the_stories_listing(self):
        navigator = _Navigator()
        page = _page(_Interactor([".text-fit-inner"]), navigator)
        asyncio.run(page.open_stories())
        assert navigator.visited == ["https://totale.rosettastone.com/stories"]

    def test_enters_the_first_tile_and_returns_its_title(self):
        interactor = _Interactor([".text-fit-inner"])
        story = asyncio.run(_page(interactor).enter_first_story())
        assert story == "Cats"
        assert interactor.clicked

    def test_falls_back_to_the_other_known_tile_shapes(self):
        # Solo responde el selector de enlaces: el listado se pintó de otra forma.
        interactor = _Interactor(["a[href*='/stories/']"])
        story = asyncio.run(_page(interactor).enter_first_story())
        assert story == "Cats"
        assert ".text-fit-inner" in interactor.asked

    def test_without_tiles_it_records_where_it_ended_up(self, monkeypatch):
        # Sin espera real: el test no puede tardar el minuto del sondeo.
        monkeypatch.setattr(stories_module, "TILE_WAIT_SECONDS", 2)
        monkeypatch.setattr(stories_module, "TILE_POLL_SECONDS", 1)

        async def _instant(_seconds):
            return None

        monkeypatch.setattr(stories_module.asyncio, "sleep", _instant)

        dumper = _Dumper()
        navigator = _Navigator(title="Inicia sesión")
        story = asyncio.run(
            _page(_Interactor(), navigator, dumper).enter_first_story()
        )

        assert story is None
        assert dumper.screenshots == ["stories_sin_listado"]
        assert dumper.meta[0][1]["titulo"] == "Inicia sesión"

    def test_a_session_without_a_dumper_still_gives_up_cleanly(self, monkeypatch):
        monkeypatch.setattr(stories_module, "TILE_WAIT_SECONDS", 1)
        monkeypatch.setattr(stories_module, "TILE_POLL_SECONDS", 1)

        async def _instant(_seconds):
            return None

        monkeypatch.setattr(stories_module.asyncio, "sleep", _instant)
        assert asyncio.run(_page(_Interactor()).enter_first_story()) is None


class TestStoriesPagePrompts:
    def test_an_ambiguous_prompt_is_clicked_by_first_match(self):
        """"Continuar" sale dos veces en la portada: el texto y el botón.

        Pulsar el locator entero hace saltar el modo estricto de Playwright y,
        antes de este arreglo, eso reventaba la corrida entera.
        """
        interactor = _Interactor([".text-fit-inner"], labels={"Continuar"})
        asyncio.run(_page(interactor).open_stories())
        assert interactor.clicked_first == ["Continuar"]

    def test_a_prompt_that_refuses_to_be_clicked_does_not_sink_the_run(self):
        interactor = _Interactor(
            [".text-fit-inner"],
            labels={"Continuar"},
            click_first_raises=RuntimeError("strict mode violation"),
        )
        story = asyncio.run(_page(interactor).enter_first_story())
        assert story == "Cats"

