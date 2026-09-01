"""Lee el panel del aprendiz (prism) para contrastar lo que envía el bot.

Todo lo que mandamos es a ciegas: el tracking contesta 200 y no dice si la
hora quedó registrada. Este endpoint es el otro lado — el número que ve la
institución — así que permite comparar una cuenta antes y después.

Es una lectura de mejor esfuerzo por diseño: sin token, con un 403 o con un
esquema cambiado devuelve ``None`` y la corrida sigue. Verificar nunca debe
romper lo que estaba verificando.

Auth: Bearer del servicio de login (no el JWT de gaia) y el **GUID** de la
cuenta, que no es el ``user_id`` numérico del tracking. Los captura
``LearnerAuthCapturer`` de la respuesta del login.
"""

from typing import Optional

from playwright.async_api import APIRequestContext

from rosseta_stone_script_a.application.ports.learner_dashboard import (
    LearnerDashboardPort,
)
from rosseta_stone_script_a.domain.values.learner_hours import LearnerHours
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin

LEARNER_DASHBOARD_URL = "https://prism.rosettastone.com/reports/learner/dashboard"


class PlaywrightLearnerDashboardAdapter(LearnerDashboardPort, LoggingMixin):
    """Implementación sobre el contexto de peticiones de Playwright."""

    def __init__(self, request_context: APIRequestContext):
        self._request = request_context

    async def get_hours(
        self, access_token: str, user_guid: str
    ) -> Optional[LearnerHours]:
        if not access_token or not user_guid:
            self.logger.debug(
                "Panel del aprendiz: falta access_token o user_guid; no se consulta"
            )
            return None

        url = f"{LEARNER_DASHBOARD_URL}/{user_guid}?skipLastUsageDate=true"
        try:
            response = await self._request.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if not response.ok:
                self.logger.warning(
                    "Panel del aprendiz respondió %s; sin horas que reportar",
                    response.status,
                )
                return None
            payload = await response.json()
        except Exception as error:  # noqa: BLE001 - comprobar no puede tumbar la corrida
            self.logger.warning("No se pudo leer el panel del aprendiz: %s", error)
            return None

        if not isinstance(payload, dict):
            self.logger.warning("El panel del aprendiz devolvió algo que no es un objeto")
            return None

        hours = LearnerHours.from_activities(
            payload.get("name", ""), payload.get("allTimeActivities") or {}
        )
        self.logger.info(
            "Panel del aprendiz: %.3f h totales, %.3f h de curso",
            hours.total_hours,
            hours.elearning_hours,
        )
        return hours
