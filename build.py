"""Build a single-file .exe with PyInstaller.

Usage:
    uv run --group dev python build.py

The .exe is written to dist/Resolucion-script-rossetta.exe. It reads its .env from the
folder the .exe sits in, and uses a system-installed browser (Chrome/Edge), so
the target machine does not need `playwright install`.
"""

import PyInstaller.__main__

PyInstaller.__main__.run([
    "src/Resolucion_script_rosseta/__main__.py",
    "--onefile",
    "--name=Resolucion-script-rossetta",
    "--console",
    "--clean",
    "--noconfirm",
    "--paths=src",
    # Bundle the Playwright Python package + its node driver.
    "--collect-all=playwright",
])
