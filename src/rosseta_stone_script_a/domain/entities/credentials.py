from dataclasses import dataclass

from rosseta_stone_script_a.domain.values.email import Email


@dataclass(frozen=True)
class Credentials:
    email: Email
    password: str
