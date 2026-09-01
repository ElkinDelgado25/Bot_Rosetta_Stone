"""Per-profile storage of the session tokens a run captures.

The CLI captures five values from the browser's outgoing traffic and uses them
in memory for that run only. The web UI keeps varios usuarios, so each profile
gets its own copy: ``sessions/<profile_id>.json`` inside the state directory,
written with owner-only permissions.

These are live credentials — the JWT and the session token authenticate as the
account. They are written to disk (the CLI already dumps raw responses under
``logs/diagnostics/``) but they are never returned whole over HTTP: ``masked()``
is what the API serves. Anyone who needs the real value reads the file.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# The five values `is_complete()` checks for, plus the detected product.
SESSION_KEYS = (
    "authorization",
    "session_token",
    "school_id",
    "user_id",
    "lang_code",
    "assessment_id",
    "product",
    # Panel del aprendiz: bearer del login y el GUID de la cuenta (que no es el
    # user_id numérico del tracking), más las horas que la plataforma reconoce.
    "access_token",
    "user_guid",
    "hours_total",
    "hours_elearning",
)

# Which of those are credentials rather than identifiers.
SECRET_KEYS = ("authorization", "session_token", "access_token")


class SessionStore:
    """Reads and writes the captured session of each profile."""

    def __init__(self, state_dir: Path) -> None:
        self._dir = Path(state_dir) / "sessions"

    def _path(self, profile_id: str) -> Path:
        return self._dir / f"{profile_id}.json"

    def save(self, profile_id: str, captured: dict[str, Any]) -> dict[str, Any]:
        """Persist the tokens found in *captured*. Returns what was stored."""
        payload = {key: captured.get(key) for key in SESSION_KEYS if captured.get(key)}
        if not payload:
            return {}
        payload["captured_at"] = datetime.now(timezone.utc).isoformat()

        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._path(profile_id)
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
        return payload

    def load(self, profile_id: str) -> dict[str, Any]:
        path = self._path(profile_id)
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, json.JSONDecodeError):
            return {}

    def delete(self, profile_id: str) -> None:
        self._path(profile_id).unlink(missing_ok=True)

    def masked(self, profile_id: str) -> dict[str, Any]:
        """The API-safe view: identifiers in the clear, secrets fingerprinted."""
        stored = self.load(profile_id)
        if not stored:
            return {}
        view: dict[str, Any] = {"captured_at": stored.get("captured_at")}
        for key in SESSION_KEYS:
            value = stored.get(key)
            if value is None:
                continue
            view[key] = _mask(value) if key in SECRET_KEYS else value
        return view


def _mask(value: str) -> str:
    """Enough to tell two tokens apart, not enough to use one."""
    text = str(value)
    if len(text) <= 10:
        return "•" * len(text)
    return f"{text[:6]}…{text[-4:]} ({len(text)} car.)"
