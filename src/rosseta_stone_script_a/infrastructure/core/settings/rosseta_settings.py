from typing import List, Union

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from rosseta_stone_script_a.infrastructure.core.base_dir import get_base_dir

_ENV_FILE = str(get_base_dir() / ".env")


class RosettaSettings(BaseSettings):
    rosetta_base_url: str = "https://www.rosettastone.com"
    rosetta_login_url: str = "https://login.rosettastone.com/login"
    rosetta_email: str | None = None
    rosetta_password: str | None = None
    rosetta_units_to_complete: List[int] = []
    rosetta_lessons_to_complete: List[int] = (
        []
    )  # Lecciones específicas a completar (vacío = todas)
    rosetta_path_types_to_complete: List[str] = (
        []
    )  # Tipos de paths/hitos a completar (vacío = todos)

    # Progress and timing settings
    rosetta_target_score_percent: int = 100
    rosetta_max_start_time_offset_ms: int = 300000  # ~5 minutos (era ~5 días)
    rosetta_inter_path_delay_ms: int = 500  # legado — sustituido por min/max
    rosetta_inter_path_delay_min_ms: int = 1500  # retraso mínimo entre paths (ms)
    rosetta_inter_path_delay_max_ms: int = 5000  # retraso máximo entre paths (ms)
    rosetta_force_recomplete: bool = (
        True  # Force re-complete even if marked as complete
    )

    # Modo de velocidad: rápido por defecto (sin topes de lote/diarios ni esperas
    # entre paths). Pon ROSETTA_HUMAN_MODE=true para el ritmo humano gradual.
    rosetta_human_mode: bool = False

    # Configuración de lote por ejecución (solo en modo humano gradual)
    rosetta_batch_min_paths: int = 6   # mínimo de paths por ejecución
    rosetta_batch_max_paths: int = 14  # máximo de paths por ejecución
    rosetta_max_paths_per_day: int = 18  # tope diario total entre todas las ejecuciones

    # Directorio de estado por cuenta (ruta relativa al directorio base)
    rosetta_state_dir: str = "state"  # subcarpeta dentro del directorio base del bot

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    @field_validator("rosetta_units_to_complete", mode="before")
    @classmethod
    def parse_units_to_complete(cls, v: Union[str, List[int]]) -> List[int]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("rosetta_lessons_to_complete", mode="before")
    @classmethod
    def parse_lessons_to_complete(cls, v: Union[str, List[int]]) -> List[int]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        return v

    @field_validator("rosetta_path_types_to_complete", mode="before")
    @classmethod
    def parse_path_types_to_complete(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if not v.strip():
                return []
            return [x.strip() for x in v.split(",") if x.strip()]
        return v
