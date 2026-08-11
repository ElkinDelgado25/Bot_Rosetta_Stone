from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .filters import ExcludePathFilter
from .formatters import (
    ErrorFileFormatter,
    FileFormatter,
    JsonFormatter,
    RelPathFormatter,
)
from .options import LoggingOptions
from .utils import detect_project_root


def _formatter_entry(use_json: bool, project_root: Path) -> Dict[str, Any]:
    if use_json:
        return {
            "json": {
                "()": JsonFormatter,
                "project_root": project_root,
            }
        }
    return {
        "detailed": {
            "()": RelPathFormatter,
            "format": "[{asctime}] {levelname} - {relpath}:{lineno} in {funcName}() - {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "project_root": project_root,
        },
        "console": {
            "()": RelPathFormatter,
            "format": "{levelname} - {relpath}:{lineno} - {message}",
            "style": "{",
            "datefmt": "%Y-%m-%d %H:%M:%S",
            "project_root": project_root,
        },
        "file": {
            "()": FileFormatter,
            "project_root": project_root,
        },
        "error_file": {
            "()": ErrorFileFormatter,
            "project_root": project_root,
        },
    }


def _make_file_handler_dict(name: str, opts, default_formatter: str) -> Dict[str, Any]:
    if not opts.enabled or opts.filename is None:
        return {}
    base = {
        "class": "logging.handlers.RotatingFileHandler",
        "level": opts.level,
        "formatter": default_formatter,
        "filename": str(opts.filename),
        "encoding": opts.encoding,
        "filters": list(opts.filters),
        "delay": opts.delay,
    }
    if opts.rotation == "size":
        base.update({"maxBytes": opts.max_bytes, "backupCount": opts.backup_count})
    elif opts.rotation == "time":
        # TimedRotatingFileHandler via dictConfig => class name distinta
        base["class"] = "logging.handlers.TimedRotatingFileHandler"
        base.update(
            {
                "when": opts.when,
                "interval": opts.interval,
                "backupCount": opts.backup_count,
                "utc": False,
            }
        )
    elif opts.rotation == "none":
        base["class"] = "logging.FileHandler"
    return {name: base}


def build_config(options: LoggingOptions) -> Dict[str, Any]:
    # Raíz del proyecto y logs dir
    project_root = options.project_root or detect_project_root()
    log_dir = options.log_dir or (project_root / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # Formatters
    fmts = _formatter_entry(options.use_json_formatter, project_root)

    # Select appropriate formatters based on mode
    if options.use_json_formatter:
        file_formatter = "json"
        error_formatter = "json"
        console_fmt = "json"
    else:
        file_formatter = "file"
        error_formatter = "error_file"
        console_fmt = "console"

    # Handlers
    handlers: Dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "level": options.console.level,
            "formatter": console_fmt,
            "stream": "ext://sys.stdout",
            "filters": list(options.console.filters),
        }
    }
    handlers.update(
        _make_file_handler_dict("file_info", options.file_info, file_formatter)
    )
    handlers.update(
        _make_file_handler_dict("file_error", options.file_error, error_formatter)
    )

    # Si no hay file handlers activos, evitamos referenciarlos en loggers/root
    active_file_handlers = [h for h in ("file_info", "file_error") if h in handlers]

    app_handlers = ["console"] + active_file_handlers

    return {
        "version": 1,
        "disable_existing_loggers": options.disable_existing_loggers,
        "formatters": fmts,
        "filters": {
            "exclude_venv": {
                "()": ExcludePathFilter,
                "patterns": ["/.venv/", "/site-packages/"],
            }
        },
        "handlers": handlers,
        "loggers": {
            options.logger_name: {
                "level": options.level,
                "handlers": app_handlers,
                "propagate": options.propagate,
            }
        },
        "root": {
            "level": options.level,
            "handlers": ["console"],
        },
    }
