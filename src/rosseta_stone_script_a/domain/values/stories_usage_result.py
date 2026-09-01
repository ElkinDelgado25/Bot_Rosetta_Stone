"""El resultado de acreditar horas de Stories."""

from dataclasses import dataclass
from typing import Optional

SECONDS_PER_HOUR = 3600


@dataclass(frozen=True)
class StoriesUsageResult:
    """Cuánto tiempo de Stories quedó reportado en esta corrida.

    ``failed`` marca que la API dejó de aceptar trozos a medias. Lo ya
    acreditado sigue siendo válido: cada POST se contabiliza por separado, así
    que una corrida cortada no se deshace, solo se queda corta.
    """

    seconds_credited: int = 0
    chunks_sent: int = 0
    failed: bool = False
    error: Optional[str] = None
    story: Optional[str] = None

    @property
    def hours_credited(self) -> float:
        return round(self.seconds_credited / SECONDS_PER_HOUR, 3)
