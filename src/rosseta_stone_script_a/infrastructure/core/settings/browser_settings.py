from pydantic_settings import BaseSettings, SettingsConfigDict

from rosseta_stone_script_a.infrastructure.core.base_dir import get_base_dir

_ENV_FILE = str(get_base_dir() / ".env")


class BrowserSettings(BaseSettings):
    headless: bool = False
    slow_mo: int = 500
    viewport_width: int = 1366
    viewport_height: int = 768
    locale: str = "es-ES"
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    )

    model_config = SettingsConfigDict(
        env_file=_ENV_FILE, env_prefix="BROWSER_", extra="ignore"
    )
