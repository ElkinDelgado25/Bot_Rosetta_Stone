"""Per-user profiles for the web UI.

Each profile is one Rosetta Stone account plus the filters that account runs
with. Profiles live in ``profiles.json`` next to the ``.env`` (see
``get_base_dir``), so a container only has to mount one directory to keep both
its credentials and its progress.

Passwords are stored in plaintext, exactly like the ``.env`` the CLI already
uses. The file is written with owner-only permissions, but that is the only
protection there is — see ``_write_private``. Callers that would rather not
persist a password can leave it unset and supply it when launching the run.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from rosseta_stone_script_a.infrastructure.core import get_base_dir

PROFILES_FILENAME = "profiles.json"


@dataclass
class Profile:
    """One account and the settings its runs use."""

    id: str
    name: str
    email: str
    password: str | None = None
    units_to_complete: list[int] = field(default_factory=list)
    lessons_to_complete: list[int] = field(default_factory=list)
    path_types_to_complete: list[str] = field(default_factory=list)
    target_score_percent: int = 100
    human_mode: bool = False
    force_recomplete: bool = False
    max_paths_per_day: int = 18
    # Fluency: cuántas lecciones pendientes completar por corrida.
    # None = todas. El default del motor es 1 (pensado para una primera prueba
    # controlada desde la terminal), que desde la UI solo confunde: completaba
    # una lección y paraba.
    fluency_max_lessons: int | None = None
    # Learned from a successful run, not asked for. The tracking API's user_id
    # names the state file; the display name and product come from the session
    # the browser captured on the dashboard.
    last_user_id: str | None = None
    display_name: str | None = None
    product: str | None = None
    # Whether the last login had to pick the institutional account (uleam).
    # None = never verified.
    institution_selected: bool | None = None

    def public_dict(self) -> dict[str, Any]:
        """Serialise for the browser, replacing the password with a flag."""
        data = asdict(self)
        data.pop("password", None)
        data["has_password"] = bool(self.password)
        return data


class ProfileStore:
    """Loads and persists the profile list as a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (get_base_dir() / PROFILES_FILENAME)
        self._profiles: dict[str, Profile] = {}
        self._load()

    @property
    def path(self) -> Path:
        return self._path

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError):
            # Corrupt or unreadable file: start empty rather than refuse to
            # boot. The user can re-add profiles from the UI.
            return

        known = {f.name for f in Profile.__dataclass_fields__.values()}
        for entry in raw.get("profiles", []):
            if not isinstance(entry, dict) or "id" not in entry:
                continue
            self._profiles[entry["id"]] = Profile(
                **{k: v for k, v in entry.items() if k in known}
            )

    def _save(self) -> None:
        payload = {"profiles": [asdict(p) for p in self._profiles.values()]}
        content = json.dumps(payload, indent=2, ensure_ascii=False)
        _write_private(self._path, content)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list(self) -> list[Profile]:
        return list(self._profiles.values())

    def get(self, profile_id: str) -> Profile | None:
        return self._profiles.get(profile_id)

    def create(self, **fields: Any) -> Profile:
        profile = Profile(id=uuid.uuid4().hex[:12], **fields)
        self._profiles[profile.id] = profile
        self._save()
        return profile

    def update(self, profile_id: str, **fields: Any) -> Profile | None:
        profile = self._profiles.get(profile_id)
        if profile is None:
            return None
        for key, value in fields.items():
            if hasattr(profile, key) and key != "id":
                setattr(profile, key, value)
        self._save()
        return profile

    def delete(self, profile_id: str) -> bool:
        if self._profiles.pop(profile_id, None) is None:
            return False
        self._save()
        return True


def _write_private(path: Path, content: str) -> None:
    """Write *content* with owner-only (0o600) permissions.

    Mirrors ``first_run._write_private``: the mode is honored on POSIX and is a
    no-op for ACLs on Windows, but it keeps the credential file as locked-down
    as the platform allows.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)
