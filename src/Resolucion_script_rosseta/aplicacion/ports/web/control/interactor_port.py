# application/ports/interactor_port.py
from abc import ABC, abstractmethod
from typing import Optional, Union

from .selector import Selector


class InteractorPort(ABC):
    @abstractmethod
    async def find(self, selector: Selector, *, within=None): ...

    @abstractmethod
    async def exists(
        self,
        target: Union[Selector, object],
        timeout: int = 0,
    ) -> bool: ...

    @abstractmethod
    async def click_first(self, target: Union[Selector, object]): ...

    @abstractmethod
    async def click(self, target: Union[Selector, object], **kwargs): ...

    @abstractmethod
    async def fill(self, target: Union[Selector, object], text: str, **kwargs): ...

    @abstractmethod
    async def press(
        self,
        key: str,
        target: Optional[Union[Selector, object]] = None,
        *args,
        **kwargs,
    ): ...

    @abstractmethod
    async def get_text(
        self,
        target: Union[Selector, object],
        timeout: int = 5000,
    ) -> Optional[str]:
        """Get the text content of an element."""
        ...

    # # Fallback and helper methods as specified in requirements
    # @abstractmethod
    # async def fill_first(self, candidates: List[Selector], text: str) -> bool:
    #     """Try to fill text in first available field from candidates (label, placeholder, role textbox)."""
    #     ...

    # @abstractmethod
    # async def within_frame(self, frame_selector: Optional[Selector] = None):
    #     """Context manager for interactions within a specific frame."""
    #     ...
