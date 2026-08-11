from dataclasses import dataclass

from rosseta_stone_script_a.shared.utils.compile_case_insensitive import (
    compile_case_insensitive,
)

cci = compile_case_insensitive


@dataclass(frozen=True)
class FormPatterns:
    SUBMIT = cci(r"enviar|submit|send|confirmar")
    RESET = cci(r"reset|reiniciar|limpiar|clear")
    EDIT = cci(r"editar|edit|modifier")
    ADD = cci(r"a[ñn]adir|add|agregar|nouveau")
