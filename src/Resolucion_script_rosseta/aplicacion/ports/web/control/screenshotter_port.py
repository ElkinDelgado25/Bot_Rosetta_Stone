from abc import ABC, abstractmethod
from typing import Optional


class ScreenShootterPort(ABC):
    @abstractmethod
    async def take_screenshot(self, path: Optional[str] = None) -> bytes: ...
