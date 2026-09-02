"""Carga el .env en os.environ para las lecturas que no pasan por pydantic.

Pydantic lee el .env, pero **solo para los campos que declara** (`ROSETTA_EMAIL`
y compañía). Un montón de knobs —todos los `FLUENCY_*`, `STORIES_*`,
`BROWSER_HEADLESS`, `LOG_LEVEL`…— se leen con ``os.getenv`` en sitios sueltos, y
``os.getenv`` no mira el .env: solo el entorno real del proceso.

El resultado era una trampa silenciosa: poner `FLUENCY_MAX_LESSONS=all` en el
.env no hacía nada. Se comprobó a costa propia el 02-09-2026 — una cuenta con 83
lecciones pendientes hizo **una** y paró, porque el knob se quedó en su default
de 1. El CLAUDE.md dice "Van en `.env` o en `environment:` del compose", así que
esto pasa a ser verdad para las dos vías, no solo para los campos de pydantic.

``override=False`` es deliberado: una variable real del entorno —la que monta
Docker con ``environment:``— gana sobre el .env. Así el contenedor sigue
mandando y el .env solo rellena lo que nadie fijó.
"""

import os

from .base_dir import get_base_dir


def load_env_into_environ() -> None:
    """Vuelca el .env (si existe) en os.environ sin pisar lo ya definido."""
    env_path = get_base_dir() / ".env"
    if not env_path.exists():
        return
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=str(env_path), override=False)
