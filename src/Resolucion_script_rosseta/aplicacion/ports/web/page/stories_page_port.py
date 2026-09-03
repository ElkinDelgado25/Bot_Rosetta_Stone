from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from Resolucion_script_rosseta.compartido.mixins import LoggingMixin


class StoriesPagePort(ABC, LoggingMixin):
    """Puerto de la pantalla de Stories dentro de Totale.

    Solo hace falta para una cosa: entrar en una historia. Ese paso es el que
    deja una sesión válida del lado del servidor; a partir de ahí las horas se
    reportan por API y la pantalla ya no pinta nada.
    """

    @abstractmethod
    async def open_stories(self) -> None:
        """Navega al listado de historias."""
        ...

    @abstractmethod
    async def enter_first_story(self) -> Optional[str]:
        """Abre una historia y devuelve su título, o ``None`` si no había ninguna."""
        ...

