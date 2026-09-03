"""Los argumentos con que se lanza Chromium.

Las actividades de conversación de Fluency dependen de dos de ellos, y son de
los que no se notan hasta que algo no funciona y nadie sabe por qué.
"""

import inspect

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.session import (
    playwright_browser_provider as modulo,
)

CODIGO = inspect.getsource(modulo)


class TestLaunchArgs:
    def test_audio_starts_without_a_user_gesture(self):
        """Sin esto el AudioContext no arranca y el micrófono no se habilita.

        El reproductor carga el reconocedor, dice "mic access allowed" y aun
        así deja el botón en `disabled`, esperando un gesto que un navegador
        automatizado no da de forma que Chrome acepte.
        """
        assert "--autoplay-policy=no-user-gesture-required" in CODIGO

    def test_the_microphone_permission_resolves_itself(self):
        assert "--use-fake-ui-for-media-stream" in CODIGO

    def test_automation_stays_hidden(self):
        assert "--disable-blink-features=AutomationControlled" in CODIGO

    def test_shared_memory_is_not_the_container_default(self):
        # /dev/shm pequeño hace que Chromium se caiga dentro de Docker.
        assert "--disable-dev-shm-usage" in CODIGO

