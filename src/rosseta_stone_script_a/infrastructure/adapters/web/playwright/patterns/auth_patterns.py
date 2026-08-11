"""
Authentication-related patterns used across login/signup flows.
"""

from dataclasses import dataclass

from rosseta_stone_script_a.shared.utils.compile_case_insensitive import (
    compile_case_insensitive,
)

cci = compile_case_insensitive


@dataclass(frozen=True)
class AuthPatterns:
    SIGN_IN = cci(r"iniciar\s+sesi[óo]n|sign\s+in|log\s+in|ingresar")
    SIGN_UP = cci(r"registr(?:arse|o)|sign\s+up|crear\s+cuenta")
    LOGIN_PAGE = cci(r"login|signin|acceder|entrar|iniciar")
    LOG_OUT = cci(r"cerrar\s+sesi[óo]n|sign\s+out|log\s+out|salir")
    FORGOT_PASSWORD = cci(
        r"olvid[éeaí]\s+(?:mi\s+)?contrase[ñn]a|forgot\s+password|reset\s+password"
    )
