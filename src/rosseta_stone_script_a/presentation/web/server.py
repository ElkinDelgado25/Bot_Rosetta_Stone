"""Entry point for the web UI server.

Binds to 127.0.0.1 by default. The container overrides it with
``ROSETTA_WEB_HOST=0.0.0.0``, which is required there — and is also why the
container should set ``ROSETTA_WEB_TOKEN`` before its port is reachable by
anyone else.
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    from .app import create_app

    host = os.getenv("ROSETTA_WEB_HOST", "127.0.0.1")
    port = int(os.getenv("ROSETTA_WEB_PORT", "8000"))

    if host not in ("127.0.0.1", "localhost") and not os.getenv("ROSETTA_WEB_TOKEN"):
        print(
            f"AVISO: escuchando en {host} sin ROSETTA_WEB_TOKEN. "
            "Cualquiera que alcance este puerto puede lanzar corridas "
            "con las credenciales guardadas."
        )

    uvicorn.run(create_app(), host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
