from __future__ import annotations

from time import monotonic
from typing import Iterable, Literal, Optional, Sequence, Tuple, Union

from playwright.sync_api import Frame, Locator, Page
from playwright.sync_api import TimeoutError as PWTimeout

State = Literal["visible", "attached", "hidden", "detached", "editable"]


def _all_frames_bfs(page: Page) -> Sequence[Frame]:
    """Devuelve todos los frames (incluye nested) en BFS, sin la main page."""
    # page.frames ya incluye todos los frames (incluida la raíz como frame principal),
    # pero orden no garantizado; generamos BFS partiendo de main_frame.
    queue = [page.main_frame]
    seen = {page.main_frame}
    order: list[Frame] = []

    while queue:
        f = queue.pop(0)
        for child in f.child_frames:
            if child not in seen:
                seen.add(child)
                order.append(child)
                queue.append(child)
    return order


def _try_find(
    context: Union[Page, Frame], selector: str, state: State, timeout_ms: float
) -> Optional[Locator]:
    """Intenta crear y esperar un locator en un contexto dado."""
    loc = context.locator(selector).first
    # Aseguramos attached antes de otros estados para evitar race con iframes que cargan
    if state != "attached":
        loc.wait_for(state="attached", timeout=timeout_ms)
    loc.wait_for(state=state, timeout=timeout_ms)
    return loc


def find_in_any_frame(
    page: Optional[Page],
    selector: Union[str, Iterable[str]],
    *,
    state: State = "visible",
    timeout: float = 5.0,
    per_context_ceiling_ms: int = 1500,
    ensure_enabled: bool = False,
) -> Tuple[Optional[Union[Frame, Page]], Optional[Locator]]:
    """
    Busca un Locator que cumpla `state` en la página o en cualquiera de sus iframes (incluye nested).

    Args:
        page: Playwright Page.
        selector: CSS o lista de selectores. Se prueban en orden (primero que coincida gana).
        state: 'visible' (por defecto), 'attached', 'hidden', 'detached' o 'editable'.
        timeout: Tiempo total (segundos) como deadline global para toda la búsqueda.
        per_context_ceiling_ms: Límite superior por contexto (frames) para no agotar el deadline en uno solo.
        ensure_enabled: Si True, además verifica `locator.is_enabled()` antes de devolver.

    Returns:
        (contexto, locator) o (None, None) si no se encuentra dentro del timeout total.
    """
    if page is None:
        return None, None

    selectors: list[str] = (
        list(selector)
        if isinstance(selector, Iterable) and not isinstance(selector, str)
        else [selector]
    )

    deadline = monotonic() + timeout

    # Orden de búsqueda: Page → frames BFS
    contexts: list[Union[Page, Frame]] = [page] + list(_all_frames_bfs(page))

    for ctx in contexts:
        remaining = max(0.0, deadline - monotonic())
        if remaining == 0:
            break
        # Repartimos el tiempo restante entre los contextos, con un techo razonable
        per_ctx_ms = min(per_context_ceiling_ms, int(remaining * 1000))

        for sel in selectors:
            try:
                loc = _try_find(ctx, sel, state=state, timeout_ms=per_ctx_ms)
                if ensure_enabled:
                    # `is_enabled` ya espera a que el elemento exista; le damos un pequeño margen
                    if not loc.is_enabled(timeout=per_ctx_ms):
                        continue
                return ctx, loc
            except PWTimeout:
                # No encontrado en este contexto/selector dentro del tiempo asignado → probamos el siguiente
                continue

    return None, None
