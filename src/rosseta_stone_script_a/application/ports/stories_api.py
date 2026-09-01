from abc import ABC, abstractmethod


class StoriesApiPort(ABC):
    """Puerto de la API de uso de Stories (``app_usage``, en lcp).

    Es la misma pareja de llamadas que hace el reproductor de Stories: una
    abre la sesión de uso y la otra le va sumando segundos. La autenticación
    es por **cookies** de la sesión del navegador, no por Bearer, así que el
    adaptador tiene que emitir desde un contexto que ya las tenga.
    """

    @abstractmethod
    async def start_usage_session(
        self, session_id: str, language: str, started_ago_seconds: int
    ) -> bool:
        """Abre la sesión de uso (``report_usage``).

        ``started_ago_seconds`` le dice al servidor hace cuántos segundos
        empezó la historia: con cero, toda sesión nacería en el instante justo
        de la primera llamada.
        """
        ...

    @abstractmethod
    async def report_usage(self, session_id: str, seconds: int) -> bool:
        """Suma ``seconds`` a la sesión abierta (``report_additional_usage``)."""
        ...
