"""Lazily build and cache the application settings.

Settings must not be constructed at import time: the first-run setup may
still need to create the .env file before pydantic reads it.
"""

from functools import lru_cache

from .app_settings import Settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
