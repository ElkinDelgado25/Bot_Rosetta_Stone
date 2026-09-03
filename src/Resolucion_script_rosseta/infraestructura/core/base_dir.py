"""Resolve the directory where runtime files (e.g. .env) live.

Resolution order:
1. ``ROSETTA_HOME``, when set — lets a container mount its data volume
   somewhere other than the working directory.
2. Next to the executable, when running as a PyInstaller .exe.
3. The current directory, for a normal Python process.
"""

import os
import sys
from pathlib import Path


def get_base_dir() -> Path:
    """Return the directory where the .env file should be looked up."""
    override = os.getenv("ROSETTA_HOME", "").strip()
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()
