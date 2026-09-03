"""Domain errors that callers are expected to act on.

The bot used to degrade quietly: when the browser phase failed to harvest the
five session values, the completion phase logged a warning, returned, and the
process still exited 0. A scheduler saw success, and the web UI showed a green
chip, for a run that sent nothing. These make that outcome loud.
"""

from __future__ import annotations


class RosettaError(Exception):
    """Base class for errors this project raises on purpose."""


class SessionCaptureIncomplete(RosettaError):
    """The browser phase ended without the credentials the API phase needs.

    Usually means the login did not finish: a changed selector, wrong password,
    or an institutional account whose organisation was never selected.
    """

    def __init__(self, missing: list[str], product: str | None = None) -> None:
        self.missing = list(missing)
        self.product = product
        target = f" de {product}" if product else ""
        super().__init__(
            f"La captura de sesión{target} quedó incompleta; "
            f"faltan: {', '.join(self.missing)}. "
            "No se envió nada: revisa las credenciales y el login."
        )


class BrowserGone(RosettaError):
    """El navegador se cerró mientras la corrida seguía usándolo.

    Pasa de verdad: en la corrida del 02-09-2026 a las 10:29 el navegador
    desapareció a mitad de una conversación. Cada llamada posterior reventaba
    con ``TargetClosedError`` de Playwright hasta que el traceback salió por la
    CLI y el proceso murió con código 1 — perdiendo las lecciones que faltaban
    y sin decir en ninguna línea que lo que se había caído era el navegador.

    Es un final legítimo, no un error de programación: lo que queda por hacer
    sigue pendiente para la próxima corrida y lo ya enviado está guardado.
    """

    def __init__(self, causa: str | None = None) -> None:
        self.causa = causa
        detalle = f" ({causa})" if causa else ""
        super().__init__(
            f"El navegador se cerró antes de terminar la corrida{detalle}. "
            "Lo enviado hasta ahí queda guardado; el resto sigue pendiente."
        )


class ExamAnswerUnavailable(RosettaError):
    """No verified or deterministic answer exists for an exam question."""

    def __init__(self, activity_step_id: str) -> None:
        self.activity_step_id = activity_step_id
        super().__init__(
            "No existe una respuesta verificada para la pregunta "
            f"{activity_step_id}. El examen se detuvo sin adivinar."
        )


class ExamResponseIncomplete(RosettaError):
    """Gaia returned neither another activity nor an explicit final result."""

    def __init__(self) -> None:
        super().__init__(
            "La API del examen devolvió una respuesta incompleta: no contiene "
            "otra actividad ni un resultado final confirmado."
        )
