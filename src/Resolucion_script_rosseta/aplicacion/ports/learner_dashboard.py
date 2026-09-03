from abc import ABC, abstractmethod
from typing import Optional

from Resolucion_script_rosseta.dominio.values.learner_hours import LearnerHours


class LearnerDashboardPort(ABC):
    """Puerto para leer las horas que la plataforma reconoce a una cuenta."""

    @abstractmethod
    async def get_hours(
        self, access_token: str, user_guid: str
    ) -> Optional[LearnerHours]:
        """Horas reportadas por el panel, o ``None`` si no se pudieron leer.

        Devolver ``None`` es un resultado válido, no un fallo: la lectura es
        una comprobación, y una comprobación que no se puede hacer nunca debe
        tumbar la corrida que estaba verificando.
        """
        ...

