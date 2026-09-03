from abc import ABC, abstractmethod

from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin


class OrchestratorPort(ABC, LoggingMixin):
    """Interface for orchestrator implementations that compose use cases."""

    def __init__(self):
        super().__init__()

    @abstractmethod
    async def execute(self, *args, **kwargs): ...

