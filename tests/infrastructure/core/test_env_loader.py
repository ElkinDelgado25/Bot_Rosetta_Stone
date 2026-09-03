"""El .env tiene que llegar a os.getenv, no solo a los campos de pydantic.

Trampa medida el 02-09-2026: `FLUENCY_LECCIONES_MAX=all` en el .env no hacía
nada. Pydantic lo ignora porque no es un campo suyo, y los knobs se leen con
os.getenv, que no mira el .env. Una cuenta con 83 lecciones pendientes hizo una
y paró, con el knob en su default de 1.
"""

import importlib

import pytest

env_loader = importlib.import_module(
    "Resolucion_script_rosseta.infraestructura.core.env_loader"
)


def _escribir_env(tmp_path, contenido):
    (tmp_path / ".env").write_text(contenido, encoding="utf-8")


def test_una_variable_solo_en_el_env_llega_a_os_getenv(tmp_path, monkeypatch):
    _escribir_env(tmp_path, "FLUENCY_LECCIONES_MAX=all\n")
    monkeypatch.setattr(env_loader, "get_base_dir", lambda: tmp_path)
    monkeypatch.delenv("FLUENCY_MAX_LESSONS", raising=False)

    env_loader.load_env_into_environ()

    import os

    assert os.getenv("FLUENCY_MAX_LESSONS") == "all"
    assert os.getenv("FLUENCY_LECCIONES_MAX") == "all"


def test_una_variable_real_del_entorno_gana_sobre_el_env(tmp_path, monkeypatch):
    """Docker monta las suyas con environment:; el .env no debe pisarlas."""
    _escribir_env(tmp_path, "FLUENCY_LECCIONES_MAX=all\n")
    monkeypatch.setattr(env_loader, "get_base_dir", lambda: tmp_path)
    monkeypatch.setenv("FLUENCY_MAX_LESSONS", "5")

    env_loader.load_env_into_environ()

    import os

    assert os.getenv("FLUENCY_MAX_LESSONS") == "5"


def test_el_alias_en_espanol_rellena_el_nombre_legacy(tmp_path, monkeypatch):
    _escribir_env(tmp_path, "FLUENCY_LECCIONES_MAX=all\n")
    monkeypatch.setattr(env_loader, "get_base_dir", lambda: tmp_path)
    monkeypatch.delenv("FLUENCY_MAX_LESSONS", raising=False)
    monkeypatch.delenv("FLUENCY_LECCIONES_MAX", raising=False)

    env_loader.load_env_into_environ()

    import os

    assert os.getenv("FLUENCY_MAX_LESSONS") == "all"
    assert os.getenv("FLUENCY_LECCIONES_MAX") == "all"


def test_sin_env_no_revienta(tmp_path, monkeypatch):
    monkeypatch.setattr(env_loader, "get_base_dir", lambda: tmp_path)
    env_loader.load_env_into_environ()  # no debe lanzar

