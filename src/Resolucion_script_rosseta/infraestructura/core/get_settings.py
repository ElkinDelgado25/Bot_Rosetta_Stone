"""Lazily build and cache the application settings.

Settings must not be constructed at import time: the first-run setup may
still need to create the .env file before pydantic reads it.
"""

from functools import lru_cache

from .env_loader import load_env_into_environ
from .app_settings import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_env_into_environ()
    return Settings()
