"""Qué pasa cuando el navegador se muere a mitad de corrida.

Ocurrió de verdad: en la corrida del 02-09-2026 a las 10:29 el navegador
desapareció mientras se resolvía una conversación. El contexto de peticiones
vive dentro del navegador, así que a partir de ahí *toda* llamada a gaia
reventaba. Lo que se vio fue un traceback de Playwright saliendo por la CLI
—``TargetClosedError: APIRequestContext.post``— y el proceso muerto con código
1, sin una sola línea diciendo que lo que se había caído era el navegador.

Lo que se arregla aquí es el comportamiento, no la causa de que se cerrara:

- se para en cuanto se sabe, en vez de recorrer lo que queda anotando fallos,
- se guarda lo enviado antes de salir,
- y se sale con error, porque una corrida a medias no es un éxito.
"""

import asyncio

import pytest

from Resolucion_script_rosseta.aplicacion.orchestrators.complete_fluency_orchestrator import (
    CompleteFluencyOrchestrator,
)
from Resolucion_script_rosseta.dominio.entities.fluency_catalog import FluencyCatalog
from Resolucion_script_rosseta.dominio.entities.fluency_course import (
    FluencyCourse,
    FluencySequenceRef,
)
from Resolucion_script_rosseta.dominio.entities.fluency_sequence import FluencySequence
from Resolucion_script_rosseta.dominio.errors import BrowserGone


class _ApiQueSePierde:
    """Devuelve lecciones y luego pierde el navegador en la número ``falla_en``."""

    def __init__(self, lecciones, falla_en=2):
        self.lecciones = lecciones
        self.falla_en = falla_en
        self.secuencias_pedidas = []
        self.verificaciones = 0

    async def get_catalog(self, authorization, locale=None):
        seqs = [
            FluencySequenceRef(sid, f"Lección {sid}", percent_complete=0.0)
            for sid in self.lecciones
        ]
        return FluencyCatalog(
            courses=[FluencyCourse("c1", "p", "Curso", "B1", "Tema", seqs)]
        )

    async def get_sequence(self, authorization, course_id, sequence_id, locale=None):
        self.secuencias_pedidas.append(sequence_id)
        if len(self.secuencias_pedidas) >= self.falla_en:
            raise BrowserGone("llamando a getSequence")
        # Antes de perderlo, lecciones sin actividades: al test le importa por
        # dónde llega el bucle, no lo que se manda.
        return FluencySequence(
            sequence_id=sequence_id,
            course_id=course_id,
            title="Lección",
            version=1,
            activities=[],
        )

    async def add_progress(self, authorization, user_id, messages):
        raise AssertionError("no debería enviarse nada en este test")

    async def add_usage_overhead(self, authorization, user_id, messages):
        raise AssertionError("no debería enviarse nada en este test")

    async def get_progress(self, authorization, course_id):
        self.verificaciones += 1
        return {}


class _EstadoEspia:
    def __init__(self):
        self.guardados = 0

    def is_done(self, key):
        return False

    def mark_done(self, key):
        return None

    def save(self):
        self.guardados += 1


def _orquestador(api, estado=None):
    orch = CompleteFluencyOrchestrator(api_port=api, max_lessons=None)
    orch._state = estado
    orch._state_for = lambda user_id, captured_data: estado  # type: ignore[assignment]
    return orch


def _correr(orch):
    return asyncio.run(orch.execute({"authorization": "tok", "user_id": "u1"}))


class TestNavegadorPerdido:
    def test_lo_enviado_se_guarda_antes_de_salir(self):
        """Lo único que este nivel decide de verdad.

        Que la corrida se pare y que salga con error los da la excepción sola.
        Lo que se añadió es guardar el estado **antes** de dejarla subir: sin
        eso, las lecciones ya enviadas en esa corrida se reenvían en la
        siguiente porque nadie las marcó.
        """
        estado = _EstadoEspia()
        api = _ApiQueSePierde(["s1", "s2"], falla_en=1)
        with pytest.raises(BrowserGone):
            _correr(_orquestador(api, estado))
        assert estado.guardados >= 1

    def test_no_se_verifica_con_el_navegador_muerto(self):
        api = _ApiQueSePierde(["s1", "s2"], falla_en=1)
        with pytest.raises(BrowserGone):
            _correr(_orquestador(api, _EstadoEspia()))
        assert api.verificaciones == 0

