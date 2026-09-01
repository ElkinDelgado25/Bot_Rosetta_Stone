"""Pesca el identificador de sesión que inventa el reproductor de Stories.

Si el propio reproductor ya abrió una sesión de uso, hay que sumarle segundos
a *esa* y no abrir otra en paralelo: dos sesiones a la vez para la misma
historia es justo lo que no hace un cliente real.

El identificador viaja en el cuerpo de la petición ``report_usage`` que emite
el JS, así que se lee de ahí. Si no aparece, el orquestador abre la suya.
"""

import json
from typing import Any, Optional

from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin

REPORT_USAGE_MARKER = "app_usage/report_usage"


class StoriesSessionCapturer(LoggingMixin):
    """Callback síncrono para ``page.on("request")``."""

    def __init__(self):
        super().__init__()
        self.session_identifier: Optional[str] = None

    def handle_request(self, request: Any) -> None:
        try:
            if REPORT_USAGE_MARKER not in (getattr(request, "url", "") or ""):
                return
            if self.session_identifier:
                return

            payload = json.loads(getattr(request, "post_data", None) or "{}")
            if not isinstance(payload, dict):
                return

            captured = payload.get("session_identifier")
            if captured:
                self.session_identifier = str(captured)
                self.logger.info(
                    "[StoriesCapture] El reproductor ya abrió una sesión de uso"
                )
        except Exception as error:  # noqa: BLE001 - una petición ilegible no es un fallo
            self.logger.debug("[StoriesCapture] Petición no utilizable: %s", error)

    def get_session_identifier(self) -> Optional[str]:
        return self.session_identifier
