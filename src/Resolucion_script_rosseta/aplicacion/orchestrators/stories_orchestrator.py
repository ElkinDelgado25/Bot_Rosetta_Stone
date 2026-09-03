"""Acredita horas de estudio a través de Stories.

La lógica, en corto:

1. Entrar en una historia con el navegador. **Ese paso no es decorativo**: es
   lo que deja una sesión válida del lado del servidor. Sin él, los POST de
   uso no tienen a qué colgarse.
2. Si el propio reproductor ya abrió su sesión de uso, se reutiliza su
   ``session_identifier``; si no, se abre una con ``report_usage``.
3. Sumarle segundos con ``report_additional_usage``, en trozos del tamaño que
   emite el cliente real, hasta cubrir el presupuesto de la corrida.

Por qué en trozos y no un POST con el total: el reproductor no manda un
resumen al final, va reportando tramos según avanza la historia. Y por qué
``started_ago`` vale el primer trozo: le dice al servidor que la historia
empezó hace ese rato, en vez de nacer en el instante exacto de la primera
llamada.

Un trozo rechazado corta la corrida pero no la deshace: cada POST se
contabiliza por separado, así que lo ya acreditado sigue contando.
"""

import asyncio
import uuid
from typing import Any, Callable, List, Optional

from Resolucion_script_rosseta.aplicacion.ports.orchestrator import OrchestratorPort
from Resolucion_script_rosseta.aplicacion.ports.stories_api import StoriesApiPort
from Resolucion_script_rosseta.aplicacion.ports.web.page import StoriesPagePort
from Resolucion_script_rosseta.aplicacion.services.stories_session_capturer import (
    StoriesSessionCapturer,
)
from Resolucion_script_rosseta.aplicacion.services.stories_usage_planner import (
    StoriesUsagePlanner,
)
from Resolucion_script_rosseta.dominio.values.stories_usage_result import (
    StoriesUsageResult,
)

# Margen para que el reproductor emita su propio report_usage, si va a hacerlo.
PLAYER_SETTLE_SECONDS = 4


class StoriesOrchestrator(OrchestratorPort):
    """Entra en una historia y reporta el tiempo de estudio de la corrida."""

    def __init__(
        self,
        stories_page: StoriesPagePort,
        stories_api: StoriesApiPort,
        planner: StoriesUsagePlanner,
        session_capturer: Optional[StoriesSessionCapturer] = None,
        network_monitor: Any = None,
        language: str = "ENG",
        delay_seconds: float = 0.0,
        sleep: Callable = asyncio.sleep,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
    ):
        super().__init__()
        self.stories_page = stories_page
        self.stories_api = stories_api
        self.planner = planner
        self.session_capturer = session_capturer or StoriesSessionCapturer()
        self.network_monitor = network_monitor
        self.language = language
        self.delay_seconds = delay_seconds
        self._sleep = sleep
        self._id_factory = id_factory

    async def execute(self, target_hours: float) -> StoriesUsageResult:
        total_seconds = self.planner.hours_to_seconds(target_hours)
        if total_seconds <= 0:
            self.logger.info("Sin presupuesto de horas: no hay nada que reportar")
            return StoriesUsageResult(error="Presupuesto de horas vacío")

        story = await self._enter_story()
        if story is None:
            return StoriesUsageResult(
                failed=True, error="No se pudo abrir ninguna historia"
            )

        chunks = self.planner.chunks(total_seconds)
        session_id = await self._usage_session(chunks)
        if session_id is None:
            return StoriesUsageResult(
                failed=True, story=story, error="No se pudo abrir la sesión de uso"
            )

        return await self._report_chunks(session_id, chunks, story)

    async def _enter_story(self) -> Optional[str]:
        """Abre una historia, escuchando de paso lo que emita el reproductor."""
        listening = self._listen_for_player()
        try:
            await self.stories_page.open_stories()
            story = await self.stories_page.enter_first_story()
            if story is None:
                return None
            # Darle su momento al reproductor antes de decidir de quién es la
            # sesión de uso: la suya siempre es preferible a una inventada.
            await self._sleep(PLAYER_SETTLE_SECONDS)
            return story
        finally:
            if listening:
                self.network_monitor.remove_request_listener(
                    self.session_capturer.handle_request
                )

    def _listen_for_player(self) -> bool:
        if self.network_monitor is None:
            return False
        self.network_monitor.add_request_listener(self.session_capturer.handle_request)
        return True

    async def _usage_session(self, chunks: List[int]) -> Optional[str]:
        """El identificador al que sumarle segundos, o ``None`` si no hubo forma."""
        captured = self.session_capturer.get_session_identifier()
        if captured:
            self.logger.info("Reutilizando la sesión de uso del reproductor")
            return captured

        session_id = self._id_factory()
        started_ago = chunks[0] if chunks else 0
        opened = await self.stories_api.start_usage_session(
            session_id, self.language, started_ago
        )
        if not opened:
            self.logger.error("report_usage no aceptó la sesión; se aborta")
            return None
        self.logger.info("Sesión de uso propia abierta")
        return session_id

    async def _report_chunks(
        self, session_id: str, chunks: List[int], story: str
    ) -> StoriesUsageResult:
        credited = 0
        sent = 0
        for chunk in chunks:
            if not await self.stories_api.report_usage(session_id, chunk):
                self.logger.error(
                    "report_additional_usage falló tras %.3f h; se detiene aquí",
                    credited / 3600,
                )
                return StoriesUsageResult(
                    seconds_credited=credited,
                    chunks_sent=sent,
                    failed=True,
                    story=story,
                    error="La API dejó de aceptar tiempo de uso",
                )
            credited += chunk
            sent += 1
            if self.delay_seconds:
                await self._sleep(self.delay_seconds)

        self.logger.info(
            "Stories: %.3f h acreditadas en %d envíos", credited / 3600, sent
        )
        return StoriesUsageResult(
            seconds_credited=credited, chunks_sent=sent, story=story
        )

