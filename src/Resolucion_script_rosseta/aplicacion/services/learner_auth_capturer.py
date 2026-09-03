"""Cosecha las credenciales que pide el panel del aprendiz.

La sesión que ya capturamos no sirve para leer ese panel: lo sirve prism, que
quiere el bearer del servicio de login y el **GUID** de la cuenta — un
identificador distinto del ``user_id`` numérico que usa el tracking.

Ambos viajan en el cuerpo de la respuesta del login, así que este capturador
escucha *respuestas*, no peticiones como los otros dos. Leer el cuerpo es
asíncrono; por eso ``handle_response`` es una corrutina y el monitor de red la
agenda en el bucle de eventos.
"""

from typing import Any, Dict, Optional

from Resolucion_script_rosseta.compartido.mixins.loggin_mixin import LoggingMixin

LOGIN_RESPONSE_MARKER = "authentication/login"


class LearnerAuthCapturer(LoggingMixin):
    """Extrae ``access_token`` y ``user_guid`` de la respuesta del login."""

    def __init__(self):
        super().__init__()
        self.captured_data: Dict[str, Optional[str]] = {
            "access_token": None,
            "user_guid": None,
        }

    async def handle_response(self, response: Any) -> None:
        """Callback para ``page.on("response")``. Nunca lanza."""
        try:
            url = getattr(response, "url", "") or ""
            if LOGIN_RESPONSE_MARKER not in url or self.is_complete():
                return

            body = await response.json()
            if not isinstance(body, dict):
                return

            auth_data = body.get("auth_data")
            if not isinstance(auth_data, dict):
                return

            self.captured_data["access_token"] = auth_data.get("access_token") or None
            self.captured_data["user_guid"] = auth_data.get("userId") or None

            if self.is_complete():
                self.logger.info(
                    "[ResponseCapture] Credenciales del panel del aprendiz capturadas"
                )
        except Exception as error:  # noqa: BLE001 - una respuesta ilegible no es un fallo
            self.logger.debug("[ResponseCapture] Respuesta de login no utilizable: %s", error)

    def is_complete(self) -> bool:
        """¿Tenemos las dos piezas que el panel necesita?"""
        return all(self.captured_data.values())

    def get_captured_data(self) -> Dict[str, Optional[str]]:
        return dict(self.captured_data)

