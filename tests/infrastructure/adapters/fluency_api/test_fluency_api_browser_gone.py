"""Un navegador muerto tiene que decir que es un navegador muerto.

Ocurrió en la corrida del 02-09-2026 a las 10:29: el navegador desapareció a
mitad de una conversación. El contexto de peticiones vive dentro del navegador,
así que desde ahí toda llamada a gaia reventaba con ``TargetClosedError``. Se
vio de dos formas, las dos malas:

- por ``_post`` (getSequence, getCatalog): el error de Playwright subía crudo
  hasta la CLI, traceback y código 1, sin una línea que nombrara al navegador.
- por ``add_progress``: peor, porque **no** subía. Ese método atrapa todo y
  devuelve un resultado de fallo, así que la corrida habría seguido recorriendo
  las actividades que quedaban anotando un fallo detrás de otro.

Lo que se traduce aquí es eso: ``TargetClosedError`` -> ``BrowserGone``, en el
adaptador, porque ``application/`` no puede importar Playwright.
"""

import asyncio

import pytest
from playwright._impl._errors import TargetClosedError

from Resolucion_script_rosseta.dominio.errors import BrowserGone
from Resolucion_script_rosseta.infraestructura.adapters.fluency_api.playwright_fluency_api import (
    PlaywrightFluencyApiAdapter,
)


class _ContextoMuerto:
    """Como Playwright cuando el navegador ya no está."""

    async def post(self, url, headers=None, data=None):
        raise TargetClosedError("Target page, context or browser has been closed")


class _ContextoQueFallaDeOtraForma:
    async def post(self, url, headers=None, data=None):
        raise RuntimeError("la red se cayó un momento")


def _adaptador(contexto):
    return PlaywrightFluencyApiAdapter(contexto)  # type: ignore[arg-type]


class TestNavegadorMuerto:
    def test_una_lectura_dice_que_fue_el_navegador(self):
        adaptador = _adaptador(_ContextoMuerto())
        with pytest.raises(BrowserGone) as caida:
            asyncio.run(adaptador.get_catalog("tok"))
        assert "navegador" in str(caida.value).lower()

    def test_un_envio_para_la_corrida_en_vez_de_anotar_un_fallo_mas(self):
        """El caso peor: add_progress atrapa todo y devolvía fallo normal.

        Así la corrida seguía recorriendo lo que quedaba fingiendo que cada
        actividad fallaba por su cuenta, cuando lo que pasaba es que ya no iba
        a funcionar ninguna.
        """
        adaptador = _adaptador(_ContextoMuerto())
        with pytest.raises(BrowserGone):
            asyncio.run(
                adaptador.add_progress("tok", "u1", [{"activityId": "a1"}])
            )

    def test_un_fallo_normal_de_envio_sigue_siendo_un_resultado_no_una_excepcion(self):
        """No se puede convertir cualquier error en 'se acabó la corrida'.

        Una caída de red puntual es de esta actividad; el navegador muerto es
        de todas. Confundirlas hundiría corridas que solo tenían un mal rato.
        """
        adaptador = _adaptador(_ContextoQueFallaDeOtraForma())
        resultado = asyncio.run(
            adaptador.add_progress("tok", "u1", [{"activityId": "a1"}])
        )
        assert resultado.success is False
        assert resultado.activity_id == "a1"

