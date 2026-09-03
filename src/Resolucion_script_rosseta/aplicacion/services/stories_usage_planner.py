"""Parte un presupuesto de horas en los trozos que reporta el reproductor.

El reproductor de Stories no manda un total al final: va sumando tramos según
avanza la historia. Un único POST con las horas enteras no se parece a nada que
emita el cliente real, así que el presupuesto se corta en trozos del tamaño de
los suyos.

El calibre por defecto (5-15 min) sale del cliente observado. El ``rng`` se
inyecta para que los tests no dependan del azar.
"""

import random
from typing import List, Optional

DEFAULT_CHUNK_MIN_SEC = 300
DEFAULT_CHUNK_MAX_SEC = 900


class StoriesUsagePlanner:
    """Convierte un total de segundos en una lista de trozos a reportar."""

    def __init__(
        self,
        chunk_min_sec: int = DEFAULT_CHUNK_MIN_SEC,
        chunk_max_sec: int = DEFAULT_CHUNK_MAX_SEC,
        rng: Optional[random.Random] = None,
    ):
        # Un mínimo mayor que el máximo es configuración inválida, no un caso
        # a resolver a medias: se ordenan y se sigue.
        self.chunk_min_sec = max(1, min(chunk_min_sec, chunk_max_sec))
        self.chunk_max_sec = max(1, max(chunk_min_sec, chunk_max_sec))
        self._rng = rng or random.Random()

    def chunks(self, total_seconds: int) -> List[int]:
        """Los trozos que suman exactamente ``total_seconds``.

        El último se ajusta al resto, así que puede ser menor que el mínimo:
        acreditar de más sería peor que un tramo corto.
        """
        remaining = int(total_seconds)
        if remaining <= 0:
            return []

        plan: List[int] = []
        while remaining > 0:
            chunk = min(remaining, self._rng.randint(self.chunk_min_sec, self.chunk_max_sec))
            plan.append(chunk)
            remaining -= chunk
        return plan

    @staticmethod
    def hours_to_seconds(hours: float) -> int:
        return max(0, int(float(hours) * 3600))
