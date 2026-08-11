# infrastructure/logging/utils.py
from __future__ import annotations

import os
from pathlib import Path


def detect_project_root() -> Path:
    # ROSETTA_HOME wins so logs land in the container's data volume instead of
    # next to the source tree, which is read-only for a non-root user.
    override = os.getenv("ROSETTA_HOME", "").strip()
    if override:
        return Path(override)

    here = Path(__file__).resolve()
    for p in here.parents:
        if any(
            (p / name).exists()
            for name in ("pyproject.toml", "setup.cfg", "setup.py", ".git")
        ):
            return p
    return (here.parents[2] if len(here.parents) >= 3 else here.parent).resolve()


def relpath(file_path: str, project_root: Path) -> str:
    try:
        return str(Path(file_path).resolve().relative_to(project_root).as_posix())
    except Exception:
        return Path(file_path).name
