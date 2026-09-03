"""Enrutado de tipos por navegador vs API, con sus knobs de env.

FLUENCY_BROWSER_EXCLUDE_TYPES saca un tipo del navegador para mandarlo por API.
Se añadió el 02-09-2026 para probar la hipótesis de que las conversaciones del
árbol se acreditaban por API mandando un AddProgress por paso.

**Resultado de esa prueba (documentado aquí para que nadie lo repita a ciegas):**
el servidor REGISTRA los envíos (attempts sube, HTTP 200) pero los califica 0 y
deja percentComplete=0. El árbol se acredita por la sesión real del navegador,
no por el score que se manda. El knob se queda como herramienta de diagnóstico,
no como ruta de completación.
"""

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    BROWSER_COMPLETED_TYPES,
)
from Resolucion_script_rosseta.presentacion.dependency_factory import DependencyFactory


def _factory():
    # _browser_completed_types solo lee env y la constante; el resto no se toca.
    return DependencyFactory(web_session=None, rosseta_login_url="http://x")


class TestBrowserCompletedTypes:
    def test_por_defecto_las_dos_conversaciones_van_por_navegador(self, monkeypatch):
        monkeypatch.delenv("FLUENCY_BROWSER_EXTRA_TYPES", raising=False)
        monkeypatch.delenv("FLUENCY_BROWSER_EXCLUDE_TYPES", raising=False)
        assert _factory()._browser_completed_types() == BROWSER_COMPLETED_TYPES

    def test_exclude_saca_un_tipo_para_enrutarlo_por_api(self, monkeypatch):
        monkeypatch.delenv("FLUENCY_BROWSER_EXTRA_TYPES", raising=False)
        monkeypatch.setenv(
            "FLUENCY_BROWSER_EXCLUDE_TYPES", "DialogueExpressionWithoutReco"
        )
        tipos = _factory()._browser_completed_types()
        assert "DialogueExpressionWithoutReco" not in tipos
        assert "DialogueExpressionWithReco" in tipos

    def test_extra_y_exclude_conviven(self, monkeypatch):
        monkeypatch.setenv("FLUENCY_BROWSER_EXTRA_TYPES", "TipoNuevo")
        monkeypatch.setenv("FLUENCY_BROWSER_EXCLUDE_TYPES", "DialogueExpressionWithReco")
        tipos = _factory()._browser_completed_types()
        assert "TipoNuevo" in tipos
        assert "DialogueExpressionWithReco" not in tipos

