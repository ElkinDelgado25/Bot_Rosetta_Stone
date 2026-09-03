# application/ports/debug_dumper.py
from abc import ABC, abstractmethod
from typing import Any, Mapping

from ..control.screenshotter_port import ScreenShootterPort


class DebugDumperPort(ABC):
    screenshotter: ScreenShootterPort

    @abstractmethod
    async def dump_text(self, tag: str, text: str) -> None: ...

    @abstractmethod
    async def dump_meta(self, tag: str, meta: Mapping[str, Any]) -> None: ...

    @abstractmethod
    async def dump_screenshot(self, tag: str) -> None: ...
