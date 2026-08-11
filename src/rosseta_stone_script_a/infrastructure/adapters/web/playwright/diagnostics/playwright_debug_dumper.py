# infrastructure/debug/file_debug_dumper.py
import re
from pathlib import Path
from typing import Any, Mapping

from rosseta_stone_script_a.application.ports.web import (
    DebugDumperPort,
    ScreenShootterPort,
)
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin


class PlaywrightFileDebugDumperAdapter(DebugDumperPort, LoggingMixin):
    def __init__(
        self, screenshotter: ScreenShootterPort, base_dir: str = "debug"
    ) -> None:
        self.base = Path(base_dir)
        self.base.mkdir(exist_ok=True)
        self.screenshotter: ScreenShootterPort = screenshotter

    def _safe_name(self, tag: str, ext: str) -> Path:
        safe = re.sub(r"[^0-9A-Za-z_.-]", "_", tag).strip("_")
        return self.base / f"{safe}{ext}"

    async def dump_text(self, tag: str, text: str) -> None:
        self._safe_name(tag, ".txt").write_text(text, encoding="utf-8")

    async def dump_meta(self, tag: str, meta: Mapping[str, Any]) -> None:
        text = "\n".join(f"{k}: {v}" for k, v in meta.items())
        await self.dump_text(tag, text)

    async def dump_screenshot(self, tag: str) -> None:
        bytes_img = await self.screenshotter.take_screenshot()
        self._safe_name(tag, ".png").write_bytes(bytes_img)
