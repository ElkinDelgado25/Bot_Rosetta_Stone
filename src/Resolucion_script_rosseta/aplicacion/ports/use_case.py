from abc import ABC, abstractmethod

from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin


class UseCasePort(ABC, LoggingMixin):
    """Interface for use case implementations."""

    @abstractmethod
    async def execute(self, *args, **kwargs): ...

