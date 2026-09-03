from abc import ABC, abstractmethod

from Resolucion_script_rosseta.dominio.entities.credentials import Credentials
from Resolucion_script_rosseta.compartido.mixins import LoggingMixin


class AuthPort(ABC, LoggingMixin):
    @abstractmethod
    async def login(self, creds: Credentials) -> None: ...

    @abstractmethod
    async def logout(self) -> None:
        """Cerrar la sesión del lado del servidor, no solo el navegador."""
        ...

