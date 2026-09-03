from abc import ABC, abstractmethod


class NavigatorPort(ABC):
    @abstractmethod
    async def go_to(self, url: str) -> None: ...

    @abstractmethod
    async def get_title(self) -> str: ...

    @abstractmethod
    async def wait_for_load(self, timeout: int = 30000) -> None: ...
