from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable


class NetworkMonitorPort(ABC):
    """Port for monitoring network traffic."""

    @abstractmethod
    def add_request_listener(
        self, listener: Callable[[Any], None]
    ) -> None:
        """Add a listener for network requests."""
        ...

    @abstractmethod
    def remove_request_listener(
        self, listener: Callable[[Any], None]
    ) -> None:
        """Remove a listener for network requests."""
        ...

    @abstractmethod
    def add_response_listener(
        self, listener: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Add a listener for network responses.

        Unlike request listeners, this one is a coroutine: reading a response
        body is asynchronous, and the body is the only place some credentials
        travel.
        """
        ...

    @abstractmethod
    def remove_response_listener(
        self, listener: Callable[[Any], Awaitable[None]]
    ) -> None:
        """Remove a listener for network responses."""
        ...
