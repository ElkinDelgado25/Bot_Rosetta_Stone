# infrastructure/logging/filters.py
from __future__ import annotations

import logging
from typing import Optional, Sequence


class ExcludePathFilter(logging.Filter):
    """Excluye logs cuyo pathname contenga patrones (/.venv/, /site-packages/, etc.)."""

    def __init__(
        self, name: str = "", patterns: Optional[Sequence[str]] = None
    ) -> None:
        super().__init__(name)
        self.patterns = [
            p.replace("\\", "/") for p in (patterns or ("/.venv/", "/site-packages/"))
        ]

    def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
        try:
            path = (getattr(record, "pathname", "") or "").replace("\\", "/")
            return not any(p in path for p in self.patterns)
        except Exception:
            return True
