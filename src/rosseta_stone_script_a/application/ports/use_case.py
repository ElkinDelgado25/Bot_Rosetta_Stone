from abc import ABC, abstractmethod

from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin


class UseCasePort(ABC, LoggingMixin):
    """Interface for use case implementations."""

    @abstractmethod
    async def execute(self, *args, **kwargs): ...
