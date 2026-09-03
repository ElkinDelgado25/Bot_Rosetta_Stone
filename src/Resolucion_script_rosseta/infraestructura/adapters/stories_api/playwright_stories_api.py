"""Cliente de la API de uso de Stories (``app_usage``, en lcp).

Son los dos POST que emite el reproductor de Stories: ``report_usage`` abre la
sesión de uso y ``report_additional_usage`` le va sumando segundos. Es la vía
que mueve las horas del panel de la institución — acelerar el ``heartbeat`` de
la sesión no reporta nada, porque el reproductor solo emite estos dos.

Auth por **cookies**, no por Bearer: el contexto de peticiones de Playwright
comparte el tarro de cookies del navegador, así que basta con emitir desde la
sesión ya autenticada. Por eso este adaptador no recibe credenciales.
"""

from typing import Any, Dict

from playwright.async_api import APIRequestContext

from Resolucion_script_rosseta.aplicacion.ports.stories_api import StoriesApiPort
from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin

LCP_BASE = "https://lcp.rosettastone.com/api/v3/app_usage"
REPORT_USAGE_URL = f"{LCP_BASE}/report_usage"
REPORT_ADDITIONAL_USAGE_URL = f"{LCP_BASE}/report_additional_usage"

TOTALE_ORIGIN = "https://totale.rosettastone.com"

APP_IDENTIFIER = "stories"
APP_VERSION = "11.11.2"


class PlaywrightStoriesApiAdapter(StoriesApiPort, LoggingMixin):
    """Implementación sobre el contexto de peticiones de Playwright."""

    def __init__(self, request_context: APIRequestContext):
        self._request = request_context

    async def start_usage_session(
        self, session_id: str, language: str, started_ago_seconds: int
    ) -> bool:
        return await self._post(
            REPORT_USAGE_URL,
            {
                "app_identifier": APP_IDENTIFIER,
                "app_version": APP_VERSION,
                "started_ago": max(0, int(started_ago_seconds)),
                "usage_length": 0,
                "language": language,
                "session_identifier": session_id,
            },
            "report_usage",
        )

    async def report_usage(self, session_id: str, seconds: int) -> bool:
        return await self._post(
            REPORT_ADDITIONAL_USAGE_URL,
            {
                "usage_length": int(seconds),
                "session_identifier": session_id,
            },
            "report_additional_usage",
        )

    async def _post(self, url: str, payload: Dict[str, Any], label: str) -> bool:
        try:
            response = await self._request.post(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Referer": f"{TOTALE_ORIGIN}/",
                    "Origin": TOTALE_ORIGIN,
                },
            )
        except Exception as error:  # noqa: BLE001 - la red se cae; la corrida lo decide
            self.logger.error("%s falló: %s", label, error)
            return False

        if not response.ok:
            self.logger.error("%s respondió %s", label, response.status)
            return False
        return True

