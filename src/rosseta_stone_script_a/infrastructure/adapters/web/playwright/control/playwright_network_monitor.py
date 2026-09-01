import asyncio
from typing import Any, Awaitable, Callable, Dict

from playwright.async_api import Page

from rosseta_stone_script_a.application.ports.web.control.network_monitor_port import (
    NetworkMonitorPort,
)


class PlaywrightNetworkMonitor(NetworkMonitorPort):
    """Playwright implementation of NetworkMonitorPort."""

    def __init__(self, page: Page):
        self._page = page
        # Playwright no espera a un handler asíncrono, así que las corrutinas se
        # registran envueltas en una tarea. Hay que recordar el envoltorio de
        # cada listener: sin él no se puede quitar lo que se puso.
        self._response_wrappers: Dict[Any, Callable[[Any], None]] = {}

    def add_request_listener(
        self, listener: Callable[[Any], None]
    ) -> None:
        self._page.on("request", listener)

    def remove_request_listener(
        self, listener: Callable[[Any], None]
    ) -> None:
        self._page.remove_listener("request", listener)

    def add_response_listener(
        self, listener: Callable[[Any], Awaitable[None]]
    ) -> None:
        def wrapper(response: Any) -> None:
            asyncio.ensure_future(listener(response))

        self._response_wrappers[listener] = wrapper
        self._page.on("response", wrapper)

    def remove_response_listener(
        self, listener: Callable[[Any], Awaitable[None]]
    ) -> None:
        wrapper = self._response_wrappers.pop(listener, None)
        if wrapper is not None:
            self._page.remove_listener("response", wrapper)
