"""El guion que captura el audio de referencia dentro de la página.

De la traza: el reproductor decodifica el audio al cargar el paso y luego
reproduce el buffer cacheado. Enganchar `decodeAudioData` solo mientras
capturamos no veía nada, porque para entonces ya no se decodifica.
"""

from Resolucion_script_rosseta.infraestructura.adapters.web.playwright.page import (
    fluency_speech_page as modulo,
)

GUION = modulo._REFERENCE_AUDIO_CAPTURE_SCRIPT


class TestCaptureScript:
    def test_remembers_every_decoded_buffer(self):
        """Sin el WeakMap, un audio decodificado antes de capturar se pierde."""
        assert "bytesPorBuffer" in GUION
        assert "WeakMap" in GUION

    def test_copies_the_bytes_before_decoding(self):
        # decodeAudioData desprende el ArrayBuffer: copiar después da vacío.
        copia = GUION.index("copia = encode(arrayBuffer.slice(0))")
        decode = GUION.index("originalDecode.call(this, arrayBuffer")
        assert copia < decode

    def test_hooks_the_moment_a_buffer_starts_playing(self):
        """Es lo que identifica el audio de la respuesta pulsada."""
        assert "AudioBufferSourceNode.prototype.start" in GUION
        assert "__rosettaLastPlayedAudio" in GUION

    def test_serialises_the_playing_buffer_to_wav(self):
        """Lo único que no depende de la URL ni del descifrado.

        La media va firmada (500 desde fuera) y se descifra en un worker donde
        estos ganchos no llegan; el AudioBuffer ya está descifrado y en el hilo
        principal, así que se leen sus muestras directamente.
        """
        assert "bufferAWav" in GUION
        assert "getChannelData" in GUION
        # Cabecera WAV completa: sin ella el navegador no la vuelve a decodificar.
        for marca in ('"RIFF"', '"WAVE"', '"fmt "', '"data"'):
            assert marca in GUION

    def test_prefers_the_original_bytes_when_it_has_them(self):
        # El WAV es reconstrucción; los bytes originales, si están, van primero.
        assert "bytesPorBuffer.get(this.buffer) || bufferAWav(this.buffer)" in GUION

    def test_keeps_the_media_element_fallback(self):
        assert "HTMLMediaElement.prototype.play" in GUION
        assert "__rosettaReferenceAudioUrl" in GUION

    def test_installs_only_once(self):
        assert "__rosettaReferenceCaptureInstalled" in GUION

    def test_keeps_a_never_reset_safety_net(self):
        """Cuando el altavoz de la respuesta no suena, sirve cualquier voz.

        ``__rosettaAnyPlayedAudio`` guarda el último audio que sonó en toda la
        página y no se reinicia entre pasos: el diálogo del enunciado también
        es voz, y con eso el reconocedor da un resultado en vez de dejar la
        corrida colgada.
        """
        assert "__rosettaAnyPlayedAudio" in GUION

    def test_it_notices_when_the_recogniser_is_ready(self):
        assert "__rosettaSreReady" in GUION
        assert "done loading speech model" in GUION

