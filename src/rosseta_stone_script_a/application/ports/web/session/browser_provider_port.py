# adapters/web/browser_provider.py
from abc import ABC, abstractmethod

from .web_session_port import IWebSession


class BrowserProviderPort(ABC):

    @abstractmethod
    async def start(self): ...

    @abstractmethod
    async def stop(self): ...
    @abstractmethod
    def new_web_session(self) -> IWebSession: ...
