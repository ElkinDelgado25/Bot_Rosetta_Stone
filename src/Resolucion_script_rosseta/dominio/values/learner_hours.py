"""Las horas de estudio que la propia plataforma reconoce a una cuenta."""

from dataclasses import dataclass
from typing import Any, Dict

MS_PER_HOUR = 3_600_000


@dataclass(frozen=True)
class LearnerHours:
    """Tiempo de estudio que reporta el panel del aprendiz, en horas.

    Es el número de Rosetta, no el nuestro: todo lo que enviamos es a ciegas
    (el tracking responde 200 sin decir si la hora se acreditó), así que esta
    es la única forma de comprobar que una corrida sirvió de algo.

    ``elearning_hours`` es la porción que el panel de la institución cuenta
    como trabajo del curso; ``total_hours`` incluye el resto de la actividad.
    """

    name: str
    total_hours: float
    elearning_hours: float

    @classmethod
    def from_activities(cls, name: str, activities: Dict[str, Any]) -> "LearnerHours":
        """Construye desde el bloque ``allTimeActivities`` del panel (en ms)."""
        return cls(
            name=name or "",
            total_hours=_to_hours(activities.get("totalTimeSpentMs")),
            elearning_hours=_to_hours(activities.get("elearningTimeSpentMs")),
        )


def _to_hours(milliseconds: Any) -> float:
    """Milisegundos a horas. Un valor ausente o ilegible vale cero, no rompe."""
    try:
        return round(float(milliseconds or 0) / MS_PER_HOUR, 3)
    except (TypeError, ValueError):
        return 0.0
