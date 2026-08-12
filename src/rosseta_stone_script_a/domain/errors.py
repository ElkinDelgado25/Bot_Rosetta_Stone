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
