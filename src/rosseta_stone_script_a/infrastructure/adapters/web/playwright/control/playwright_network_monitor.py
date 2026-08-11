from typing import Any, Callable

from playwright.async_api import Page

from rosseta_stone_script_a.application.ports.web.control.network_monitor_port import (
    NetworkMonitorPort,
)


class PlaywrightNetworkMonitor(NetworkMonitorPort):
    """Playwright implementation of NetworkMonitorPort."""

    def __init__(self, page: Page):
        self._page = page

    def add_request_listener(
        self, listener: Callable[[Any], None]
    ) -> None:
        self._page.on("request", listener)

    def remove_request_listener(
        self, listener: Callable[[Any], None]
    ) -> None:
        self._page.remove_listener("request", listener)
