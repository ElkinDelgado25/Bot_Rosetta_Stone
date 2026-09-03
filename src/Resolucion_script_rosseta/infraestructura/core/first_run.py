"""Interactive first-run setup: creates a .env file when one doesn't exist."""

import getpass
import os
from pathlib import Path

from .base_dir import get_base_dir

_MINIMAL_ENV_TEMPLATE = """\
# Resolucion script Rossetta — Configuracion
# Generado automaticamente en la primera ejecucion.
# Puedes editar este archivo para cambiar la configuracion.
# Los nombres nuevos van en español; los viejos siguen funcionando como alias.

# === Credenciales ===
ROSETTA_CORREO={email}
ROSETTA_CLAVE={password}

# === Puntaje objetivo (0-100) ===
ROSETTA_PORCENTAJE_OBJETIVO=100

# === Opciones avanzadas (descomenta para cambiar) ===
# Unidades a completar (vacio = todas).
# ROSETTA_UNIDADES_POR_COMPLETAR=1,2,3
# Tipos de paths a completar (vacio = todos).
# ROSETTA_TIPOS_POR_COMPLETAR=production_milestone
# Lote por ejecucion y tope diario.
# ROSETTA_MINIMO_PATHS_POR_LOTE=6
# ROSETTA_MAXIMO_PATHS_POR_LOTE=14
# ROSETTA_MAXIMO_PATHS_POR_DIA=18
# Navegador sin interfaz grafica.
# NAVEGADOR_SIN_GUI=true
"""


def _write_private(env_path: Path, content: str) -> None:
    """Write *content* to *env_path* with owner-only (0o600) permissions.

    The file holds the account password in plaintext, so it must not be
    world-readable. The mode is honored on POSIX; on Windows it is a no-op for
    ACLs, but writing this way keeps the credential file as locked-down as the
    platform allows.
    """
    fd = os.open(str(env_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(content)


def ensure_env_exists() -> None:
    """If .env doesn't exist next to the .exe (or CWD), run interactive setup."""
    env_path = get_base_dir() / ".env"

    if env_path.exists():
        return

    print("=" * 60)
    print("  Resolucion script Rossetta")
    print("  Primera ejecucion — Configuracion inicial")
    print("=" * 60)
    print()

    email = input("Tu email de Rosetta Stone: ").strip()
    password = getpass.getpass("Tu contrasena (no se muestra al escribir): ").strip()

    if not email or not password:
        print("\nError: Email y contrasena son obligatorios.")
        raise SystemExit(1)

    _write_private(
        env_path, _MINIMAL_ENV_TEMPLATE.format(email=email, password=password)
    )

    print(f"\nArchivo .env creado en: {env_path}")
    print("Puedes editarlo despues para cambiar la configuracion.")
    print()
