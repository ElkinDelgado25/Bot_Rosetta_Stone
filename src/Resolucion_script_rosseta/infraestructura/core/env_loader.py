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

Además, este módulo traduce alias en español hacia los nombres históricos en
inglés. Eso permite escribir los .env nuevos con nombres más legibles sin romper
el código viejo ni las instalaciones ya configuradas.
"""

import os

from .base_dir import get_base_dir

ENV_ALIASES: dict[str, str] = {
    # Rosetta general
    "ROSETTA_CORREO": "ROSETTA_EMAIL",
    "ROSETTA_CLAVE": "ROSETTA_PASSWORD",
    "ROSETTA_URL_BASE": "ROSETTA_BASE_URL",
    "ROSETTA_URL_INGRESO": "ROSETTA_LOGIN_URL",
    "ROSETTA_RAIZ": "ROSETTA_HOME",
    "ROSETTA_UNIDADES_POR_COMPLETAR": "ROSETTA_UNITS_TO_COMPLETE",
    "ROSETTA_LECCIONES_POR_COMPLETAR": "ROSETTA_LESSONS_TO_COMPLETE",
    "ROSETTA_TIPOS_POR_COMPLETAR": "ROSETTA_PATH_TYPES_TO_COMPLETE",
    "ROSETTA_PORCENTAJE_OBJETIVO": "ROSETTA_TARGET_SCORE_PERCENT",
    "ROSETTA_DESFASE_MAXIMO_INICIO_MS": "ROSETTA_MAX_START_TIME_OFFSET_MS",
    "ROSETTA_RETARDO_ENTRE_PATHS_MS": "ROSETTA_INTER_PATH_DELAY_MS",
    "ROSETTA_RETARDO_MINIMO_ENTRE_PATHS_MS": "ROSETTA_INTER_PATH_DELAY_MIN_MS",
    "ROSETTA_RETARDO_MAXIMO_ENTRE_PATHS_MS": "ROSETTA_INTER_PATH_DELAY_MAX_MS",
    "ROSETTA_MODO_HUMANO": "ROSETTA_HUMAN_MODE",
    "ROSETTA_MINIMO_PATHS_POR_LOTE": "ROSETTA_BATCH_MIN_PATHS",
    "ROSETTA_MAXIMO_PATHS_POR_LOTE": "ROSETTA_BATCH_MAX_PATHS",
    "ROSETTA_MAXIMO_PATHS_POR_DIA": "ROSETTA_MAX_PATHS_PER_DAY",
    "ROSETTA_DIRECTORIO_ESTADO": "ROSETTA_STATE_DIR",
    # Web
    "ROSETTA_HOST_WEB": "ROSETTA_WEB_HOST",
    "ROSETTA_PUERTO_WEB": "ROSETTA_WEB_PORT",
    "ROSETTA_TOKEN_WEB": "ROSETTA_WEB_TOKEN",
    "ROSETTA_BACKEND_EJECUCION": "ROSETTA_RUN_BACKEND",
    # Browser
    "NAVEGADOR_SIN_GUI": "BROWSER_HEADLESS",
    "NAVEGADOR_LENTO_MS": "BROWSER_SLOW_MO",
    "NAVEGADOR_AGENTE_USUARIO": "BROWSER_USER_AGENT",
    "NAVEGADOR_IDIOMA": "BROWSER_LOCALE",
    "NAVEGADOR_ANCHO_VENTANA": "BROWSER_VIEWPORT_WIDTH",
    "NAVEGADOR_ALTO_VENTANA": "BROWSER_VIEWPORT_HEIGHT",
    "NAVEGADOR_CANAL": "BROWSER_CHANNEL",
    # Fluency / Stories / logging
    "FLUENCY_LECCIONES_MAX": "FLUENCY_MAX_LESSONS",
    "FLUENCY_EJECUCION_DE_PRUEBA": "FLUENCY_DRY_RUN",
    "FLUENCY_HORAS_TOTALES_CURSO": "FLUENCY_TOTAL_COURSE_HOURS",
    "FLUENCY_ENVIAR_SOBRECOSTO_USO": "FLUENCY_SEND_USAGE_OVERHEAD",
    "FLUENCY_CURSO": "FLUENCY_COURSE",
    "FLUENCY_LECCION": "FLUENCY_LESSON",
    "FLUENCY_TIPOS_EXTRA_NAVEGADOR": "FLUENCY_BROWSER_EXTRA_TYPES",
    "FLUENCY_TIPOS_EXCLUIDOS_NAVEGADOR": "FLUENCY_BROWSER_EXCLUDE_TYPES",
    "FLUENCY_NAVEGADOR_VOZ": "FLUENCY_SPEECH_BROWSER",
    "FLUENCY_TRAZA_VOZ": "FLUENCY_SPEECH_TRACE",
    "FLUENCY_ARCHIVO_AUDIO_FALSO": "FLUENCY_FAKE_AUDIO_FILE",
    "FLUENCY_RUIDO_CALIBRACION_MICROFONO": "FLUENCY_MIC_CALIBRATION_NOISE",
    "FLUENCY_CAPTURAR_GAIA": "FLUENCY_CAPTURE_GAIA",
    "STORIES_HORAS_OBJETIVO": "STORIES_TARGET_HOURS",
    "STORIES_SEG_MIN_TRAMO": "STORIES_CHUNK_MIN_SEC",
    "STORIES_SEG_MAX_TRAMO": "STORIES_CHUNK_MAX_SEC",
    "STORIES_IDIOMA": "STORIES_LANGUAGE",
    "STORIES_RETARDO_REPORTE_SEG": "STORIES_REPORT_DELAY_SEC",
    "NIVEL_LOG": "LOG_LEVEL",
    # Worker and diagnostics
    "ROSETTA_IMAGEN_TRABAJADOR": "ROSETTA_WORKER_IMAGE",
    "ROSETTA_RUTA_DATOS_HOST": "ROSETTA_DATA_HOST_PATH",
    "ROSETTA_CONFIG_EJECUCION": "ROSETTA_RUN_CONFIG",
    "ROSETTA_EVENTOS": "ROSETTA_EVENTS",
}


def _mirror_aliases() -> None:
    for alias, canonical in ENV_ALIASES.items():
        alias_value = os.getenv(alias, "").strip()
        canonical_value = os.getenv(canonical, "").strip()
        if alias_value and not canonical_value:
            os.environ[canonical] = alias_value
            canonical_value = alias_value
        if canonical_value and not alias_value:
            os.environ[alias] = canonical_value


def load_env_into_environ() -> None:
    """Vuelca el .env (si existe) en os.environ sin pisar lo ya definido."""
    env_path = get_base_dir() / ".env"
    if not env_path.exists():
        _mirror_aliases()
        return
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=str(env_path), override=False)
    _mirror_aliases()
