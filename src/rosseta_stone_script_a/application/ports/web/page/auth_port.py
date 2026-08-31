from abc import ABC, abstractmethod

from rosseta_stone_script_a.domain.entities.credentials import Credentials
from rosseta_stone_script_a.shared.mixins import LoggingMixin


class AuthPort(ABC, LoggingMixin):
    @abstractmethod
    async def login(self, creds: Credentials) -> None: ...

    @abstractmethod
    async def logout(self) -> None:
        """Cerrar la sesión del lado del servidor, no solo el navegador."""
        ...
