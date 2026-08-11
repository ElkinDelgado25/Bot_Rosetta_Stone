from abc import ABC, abstractmethod

from ..control.interactor_port import InteractorPort
from ..control.navigator_port import NavigatorPort
from ..control.network_monitor_port import NetworkMonitorPort
from ..control.screenshotter_port import ScreenShootterPort
from ..diagnostics.debug_dumper_port import DebugDumperPort


class IWebSession(ABC):
    """Capacidad completa de automatización web"""

    navigator: "NavigatorPort"
    interactor: "InteractorPort"
    network_monitor: "NetworkMonitorPort"

    screenshotter: "ScreenShootterPort"
    debug_dumpper: "DebugDumperPort"

    @abstractmethod
    async def session(self) -> None: ...
    @abstractmethod
    async def close(self) -> None: ...
