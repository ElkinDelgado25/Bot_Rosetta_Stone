from dataclasses import dataclass

from Resolucion_script_rosseta.dominio.values.email import Email


@dataclass(frozen=True)
class Credentials:
    email: Email
    password: str

