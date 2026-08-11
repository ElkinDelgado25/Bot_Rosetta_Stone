"""Build a single-file .exe with PyInstaller.

Usage:
    uv run --group dev python build.py

The .exe is written to dist/rosseta-script-a.exe. It reads its .env from the
folder the .exe sits in, and uses a system-installed browser (Chrome/Edge), so
the target machine does not need `playwright install`.
"""

import PyInstaller.__main__

PyInstaller.__main__.run([
    "src/rosseta_stone_script_a/__main__.py",
    "--onefile",
    "--name=rosseta-script-a",
    "--console",
    "--clean",
    "--noconfirm",
    "--paths=src",
    # Bundle the Playwright Python package + its node driver.
    "--collect-all=playwright",
])
