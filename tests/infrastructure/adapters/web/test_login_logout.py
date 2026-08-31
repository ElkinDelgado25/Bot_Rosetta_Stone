import asyncio
from types import SimpleNamespace

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.login_page import (
    LoginPage,
)


class _Navigator:
    def __init__(self) -> None:
        self.visited: list[str] = []

    async def go_to(self, url: str, wait_for_load: bool = False) -> None:
        self.visited.append(url)


def _login_page(login_url: str) -> tuple[LoginPage, _Navigator]:
    navigator = _Navigator()
    session = SimpleNamespace(navigator=navigator)
    return LoginPage(web_session=session, rosetta_login_url=login_url), navigator


def test_logout_navigates_to_the_logout_path():
    page, navigator = _login_page("https://login.rosettastone.com/login")

    asyncio.run(page.logout())

    assert navigator.visited == ["https://login.rosettastone.com/logout"]


def test_logout_keeps_the_origin_of_the_configured_login_url():
    page, navigator = _login_page("https://login.example.test/some/login")

    asyncio.run(page.logout())

    assert navigator.visited == ["https://login.example.test/logout"]
