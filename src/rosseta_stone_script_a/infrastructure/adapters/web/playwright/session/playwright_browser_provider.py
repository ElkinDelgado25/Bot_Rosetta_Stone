from __future__ import annotations

from typing import Optional

from playwright.async_api import Browser, Playwright, async_playwright

from rosseta_stone_script_a.application.ports.web import BrowserProviderPort
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin

from ..common.viewport import Viewport
from .playwright_web_session import PlaywrightWebSession


class PlaywrightBrowserProvider(BrowserProviderPort, LoggingMixin):
    def __init__(
        self,
        *,
        headless: bool,
        slow_mo: int = 0,
        user_agent: str,
        locale: str,
        viewport: Viewport,
        enable_no_sandbox: bool = True,
    ) -> None:
        self._playwright_instance: Optional[Playwright] = None
        self.browser: Optional[Browser] = None

        self.headless = headless
        self.slow_mo = slow_mo
        self.user_agent = user_agent
        self.locale = locale

        # Validación simple del viewport
        if not isinstance(viewport.get("width"), int) or not isinstance(
            viewport.get("height"), int
        ):
            raise ValueError("viewport must have integer 'width' and 'height'")
        self.viewport = viewport

        self.enable_no_sandbox = enable_no_sandbox

    async def start(self) -> None:
        if self.browser is not None:
            return

        self._playwright_instance = await async_playwright().start()

        self._playwright_instance.selectors.set_test_id_attribute("data-qa")

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            # Sin esto Chrome no deja arrancar un AudioContext hasta que haya un
            # gesto de usuario "de verdad", y el reproductor de Fluency deja el
            # micrófono deshabilitado esperando ese arranque. Es la diferencia
            # entre que las actividades de conversación se puedan completar o no.
            "--autoplay-policy=no-user-gesture-required",
            # El reconocedor pide micrófono: que se conceda solo y que exista un
            # dispositivo falso detrás, aunque el contenedor no tenga audio.
            # Sin el segundo, el desplegable de la "Comprobación de micrófono"
            # de Fluency sale vacío y su modal no deja avanzar.
            "--use-fake-ui-for-media-stream",
            "--use-fake-device-for-media-stream",
        ]
        # Banco de pruebas: reemplaza el tono de 1 kHz del dispositivo de audio
        # falso de Chrome por una grabación de voz real ("1, 2, 3, 4, 5") en
        # bucle. HIPÓTESIS DESCARTADA (03-09-2026): se pensó que el reconocedor
        # calibraba leyendo el dispositivo y rechazaba el tono. Probado: con el
        # flag el WARMUP cambia (~500 -> ~900, o sea el audio SÍ cambió) y aun
        # así calibrateSaga se cancela cada 4.1 s igual. El timeout de
        # calibración NO depende del contenido del audio (ni del render:
        # headless falla igual). Default OFF; encendible con
        # FLUENCY_FAKE_AUDIO_FILE=1 para experimentar. Requiere WAV PCM 16-bit.
        import os as _os
        from pathlib import Path

        from rosseta_stone_script_a.infrastructure.core import get_base_dir

        if _os.getenv("FLUENCY_FAKE_AUDIO_FILE", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            base = get_base_dir()
            candidatos = [
                base / "audio" / "mic_check.wav",
                base / "data" / "audio" / "mic_check.wav",
                Path.cwd() / "data" / "audio" / "mic_check.wav",
            ]
            mic_wav = next((c for c in candidatos if c.exists()), None)
            if mic_wav is not None:
                launch_args.append(
                    f"--use-file-for-fake-audio-capture={mic_wav}"
                )
        if self.enable_no_sandbox:
            launch_args.append("--no-sandbox")

        # Prefer a system-installed browser so a packaged .exe needs no
        # `playwright install`. Order: BROWSER_CHANNEL (default chrome) ->
        # msedge (always present on Windows) -> Playwright's bundled Chromium.
        import os

        # An empty BROWSER_CHANNEL means "no channel": go straight to the
        # bundled Chromium. That is what a Linux container wants, where neither
        # Chrome nor Edge exists and trying them just costs two failed launches.
        preferred = os.getenv("BROWSER_CHANNEL", "chrome").strip() or None
        channels: list[str | None] = []
        for ch in (preferred, "msedge", None):
            if ch not in channels:
                channels.append(ch)

        last_error: Exception | None = None
        for channel in channels:
            try:
                self.browser = await self._playwright_instance.chromium.launch(
                    headless=self.headless,
                    slow_mo=self.slow_mo,
                    args=launch_args,
                    channel=channel,
                )
                break
            except Exception as exc:  # noqa: BLE001 - try the next channel
                last_error = exc
        if self.browser is None:
            raise RuntimeError(
                f"Could not launch a browser (tried channels {channels}). "
                "Install Chrome/Edge or run 'playwright install chromium'."
            ) from last_error

    async def stop(self) -> None:
        if self.browser:
            await self.browser.close()
            self.browser = None
        if self._playwright_instance:
            await self._playwright_instance.stop()
            self._playwright_instance = None

    def new_web_session(self) -> PlaywrightWebSession:
        if self.browser is None:
            raise RuntimeError("The browser is not started. Call start() first.")
        return PlaywrightWebSession(
            self.browser,
            user_agent=self.user_agent,
            locale=self.locale,
            viewport=self.viewport,
        )
