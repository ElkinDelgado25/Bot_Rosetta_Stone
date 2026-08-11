"""Resolve the directory where runtime files (e.g. .env) live.

When running as a PyInstaller .exe, files sit next to the executable.
When running as a normal Python process, files live in the current directory.
"""

import sys
from pathlib import Path


def get_base_dir() -> Path:
    """Return the directory where the .env file should be looked up."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()
