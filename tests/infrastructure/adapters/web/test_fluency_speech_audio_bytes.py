"""De dónde salen los bytes del audio de referencia.

Bajar la URL por fuera de la página devolvía 500: esa media va firmada para la
sesión de la página, y una URL ``blob:`` ni siquiera existe fuera de ella. El
orden importa: lo decodificado por el reproductor, luego una descarga dentro de
la página, y el contexto de peticiones solo como último recurso.
"""

import asyncio
import base64

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.infrastructure.adapters.web.playwright.page.fluency_speech_page import (
    PlaywrightFluencySpeechPage,
)

BYTES = b"audio-de-verdad"
EN_BASE64 = base64.b64encode(BYTES).decode()


class _Respuesta:
    def __init__(self, ok=True, status=200, cuerpo=b"desde-el-contexto"):
        self.ok = ok
        self.status = status
        self._cuerpo = cuerpo

    async def body(self):
        return self._cuerpo


class _Peticiones:
    def __init__(self, respuesta=None):
        self.respuesta = respuesta or _Respuesta()
        self.llamadas = []

    async def get(self, url):
        self.llamadas.append(url)
        return self.respuesta


class _Page:
    def __init__(
        self,
        en_pagina=None,
        respuesta=None,
        falla_en_pagina=False,
        bytes_tardios=None,
        src_del_dom="",
    ):
        self.en_pagina = en_pagina
        self.falla_en_pagina = falla_en_pagina
        self.bytes_tardios = bytes_tardios
        self.src_del_dom = src_del_dom
        self.request = _Peticiones(respuesta)
        self.evaluaciones = []
        self.descargas = 0

    async def wait_for_function(self, expression, *args, **kwargs):
        # El margen para que aparezcan los bytes decodificados.
        if self.bytes_tardios is None:
            raise PlaywrightTimeoutError("sin bytes")

    async def evaluate(self, expression, *args):
        self.evaluaciones.append(expression)
        if "__rosettaReferenceAudio ||" in expression:
            return self.bytes_tardios
        if "querySelectorAll('audio" in expression:
            return self.src_del_dom
        self.descargas += 1
        if self.falla_en_pagina:
            raise RuntimeError("fetch bloqueado")
        return self.en_pagina


def _bytes(page, captured):
    speech = PlaywrightFluencySpeechPage(page)  # type: ignore[arg-type]
    return asyncio.run(speech._reference_audio_bytes(captured))


class TestReferenceAudioBytes:
    def test_prefers_what_the_player_decoded(self):
        page = _Page()
        assert _bytes(page, {"audio": EN_BASE64, "url": "https://x/a.mp3"}) == BYTES
        # Ni se molesta en descargar nada.
        assert page.evaluaciones == [] and page.request.llamadas == []

    def test_downloads_inside_the_page_when_there_are_no_bytes(self):
        page = _Page(en_pagina=EN_BASE64)
        assert _bytes(page, {"url": "blob:https://learn/abc"}) == BYTES
        assert page.request.llamadas == []

    def test_falls_back_to_the_request_context(self):
        page = _Page(en_pagina=None)
        assert _bytes(page, {"url": "https://x/a.mp3"}) == b"desde-el-contexto"
        assert page.request.llamadas == ["https://x/a.mp3"]

    def test_a_rejected_download_returns_nothing_instead_of_raising(self):
        page = _Page(en_pagina=None, respuesta=_Respuesta(ok=False, status=500))
        assert _bytes(page, {"url": "https://x/a.mp3"}) == b""

    def test_a_blocked_page_fetch_still_tries_the_request_context(self):
        page = _Page(falla_en_pagina=True)
        assert _bytes(page, {"url": "https://x/a.mp3"}) == b"desde-el-contexto"

    def test_without_bytes_or_url_there_is_nothing_to_do(self):
        assert _bytes(_Page(), {}) == b""

    def test_bytes_that_arrive_a_moment_later_are_used(self):
        """El reproductor arranca la fuente y decodifica justo después."""
        page = _Page(bytes_tardios=EN_BASE64)
        assert _bytes(page, {"url": "https://x/a.mp3"}) == BYTES
        assert page.descargas == 0

    def test_the_dom_supplies_the_source_when_the_hooks_missed_it(self):
        page = _Page(en_pagina=EN_BASE64, src_del_dom="https://x/desde-el-dom.mp3")
        assert _bytes(page, {}) == BYTES
