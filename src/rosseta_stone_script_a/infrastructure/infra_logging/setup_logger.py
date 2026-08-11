from __future__ import annotations

import logging
import logging.config
import os
from datetime import datetime
from typing import Literal

from .config import build_config
from .options import FileHandlerOptions, LoggingOptions
from .utils import detect_project_root


def _env_level(
    default: str = "INFO",
) -> Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    env = str(default).upper()
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if env not in valid_levels:
        env = "INFO"
    return env  # type: ignore


def _setup_log_directories(logs_dir: "Path") -> dict:
    """Create organized log directory structure.

    Structure:
        logs/
        ├── app/           # Application logs (INFO+)
        │   └── app_2024-01-15.log
        ├── error/         # Error logs only (ERROR+)
        │   └── error_2024-01-15.log
        └── debug/         # Debug logs (DEBUG+) - optional
            └── debug_2024-01-15.log
    """
    from pathlib import Path

    # Create subdirectories
    app_dir = logs_dir / "app"
    error_dir = logs_dir / "error"
    debug_dir = logs_dir / "debug"

    for directory in [logs_dir, app_dir, error_dir, debug_dir]:
        directory.mkdir(parents=True, exist_ok=True)

    # Generate dated filenames
    today = datetime.now().strftime("%Y-%m-%d")

    return {
        "app": app_dir / f"app_{today}.log",
        "error": error_dir / f"error_{today}.log",
        "debug": debug_dir / f"debug_{today}.log",
    }


def _default_options() -> LoggingOptions:
    project_root = detect_project_root()
    level = _env_level(os.getenv("LOG_LEVEL", "INFO"))

    logs_dir = project_root / "logs"
    log_files = _setup_log_directories(logs_dir)

    return LoggingOptions(
        level=level,
        project_root=project_root,
        log_dir=logs_dir,
        file_info=FileHandlerOptions(
            enabled=True,
            level="INFO",
            filename=log_files["app"],
            rotation="size",
            max_bytes=10_485_760,  # 10MB
            backup_count=10,  # Keep more backups for traceability
        ),
        file_error=FileHandlerOptions(
            enabled=True,
            level="ERROR",
            filename=log_files["error"],
            rotation="size",
            max_bytes=5_242_880,  # 5MB for error logs
            backup_count=20,  # Keep more error logs for debugging
        ),
        use_json_formatter=os.getenv("LOG_JSON", "0") == "1",
    )


def setup_logging(options: LoggingOptions) -> logging.Logger:
    root = logging.getLogger()
    cfg = build_config(options)

    # Si ya hay handlers, revisa si ya existen los file handlers que necesitas.
    # Si faltan, reconfigura.
    has_file_handler = any(isinstance(h, logging.FileHandler) for h in root.handlers)

    if root.handlers and has_file_handler:
        # Ajusta nivel por si cambió
        desired = getattr(logging, options.level, logging.INFO)
        root.setLevel(desired)
        for h in root.handlers:
            h.setLevel(min(h.level or desired, desired))
        return logging.getLogger(options.logger_name)

    # Reconfigura (o configura por primera vez)
    logging.config.dictConfig(cfg)
    return logging.getLogger(options.logger_name)


def get_logger(name: str | None = None) -> logging.Logger:
    setup_logging(_default_options())
    return logging.getLogger(name or "app")
