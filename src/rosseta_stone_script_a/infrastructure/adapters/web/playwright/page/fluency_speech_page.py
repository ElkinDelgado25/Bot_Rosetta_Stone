"""Playwright workflow for Fluency conversation-practice activities.

The Gaia progress endpoint alone cannot complete ``DialogueExpressionWithReco``.
The lesson player needs a microphone MediaStream and its local speech recognizer
must produce the result. This adapter feeds the selected answer's own reference
audio into an in-page virtual microphone and lets the normal player submit it.
"""

from __future__ import annotations

import base64
import re
from typing import Any

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from rosseta_stone_script_a.application.ports.fluency_speech import FluencySpeechPort
from rosseta_stone_script_a.shared.mixins.loggin_mixin import LoggingMixin


LEARN_ORIGIN = "https://learn.rosettastone.com"

_VIRTUAL_MIC_SCRIPT = r"""
(() => {
  if (window.__rosettaVirtualMicInstalled) return;
  window.__rosettaVirtualMicInstalled = true;
  window.__rosettaMicReady = false;
  window.__rosettaMicPlaybackDone = false;

  const devices = navigator.mediaDevices;
  const original = devices.getUserMedia.bind(devices);
  const state = { context: null, destination: null };

  devices.getUserMedia = async (constraints) => {
    if (!constraints || !constraints.audio) return original(constraints);
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    state.context = state.context || new AudioContextClass({ sampleRate: 48000 });
    await state.context.resume();
    state.destination = state.context.createMediaStreamDestination();
    window.__rosettaMicReady = true;
    return state.destination.stream;
  };

  // La "Comprobación de micrófono" de Fluency lista los dispositivos y no deja
  // pasar si no hay ninguno. Un contenedor no tiene micrófonos, así que se le
  // ofrece uno: el audio real lo pone el micrófono virtual de arriba.
  if (devices.enumerateDevices) {
    const originalEnumerate = devices.enumerateDevices.bind(devices);
    devices.enumerateDevices = async () => {
      const lista = await originalEnumerate();
      if (lista.some((d) => d.kind === "audioinput")) return lista;
      return [
        ...lista,
        {
          deviceId: "default",
          kind: "audioinput",
          label: "Micrófono",
          groupId: "rosetta",
          toJSON() { return this; },
        },
      ];
    };
  }

  // El modal de "Comprobación de micrófono" no está cuando se abre la
  // actividad: aparece un momento después, así que buscarlo una vez no vale.
  // Este vigilante lo cierra en cuanto se pinta, sin depender del momento en
  // que a nosotros nos toque mirar.
  const emitirClic = (nodo) => {
    for (const tipo of ["pointerdown", "mousedown", "mouseup", "click"]) {
      const Evento = tipo.startsWith("pointer") && window.PointerEvent
        ? PointerEvent : MouseEvent;
      nodo.dispatchEvent(new Evento(tipo, {
        bubbles: true, cancelable: true, composed: true, button: 0, buttons: 1,
      }));
    }
  };

  // La comprobación pide decir "1, 2, 3, 4, 5" y escucha. Un micrófono virtual
  // sin nada inyectado es silencio, y la prueba responde "No se detectó su
  // entrada de audio". Con una señal continua conectada al destino, sí detecta.
  // Si hay una grabación real (una voz diciendo "1, 2, 3, 4, 5"), se reproduce
  // en bucle: es lo que la comprobación espera oír de verdad. El tono es el
  // recurso cuando no hay grabación.
  window.__rosettaMicCheckAudio = window.__rosettaMicCheckAudio || null;
  window.__rosettaMicCheckBuffer = null;
  window.__rosettaPrepareMicCheckAudio = async (codificado) => {
    window.__rosettaMicCheckAudio = codificado;
    try {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const contexto = state.context || new AudioContextClass({ sampleRate: 48000 });
      const binario = atob(codificado);
      const bytes = new Uint8Array(binario.length);
      for (let i = 0; i < binario.length; i += 1) bytes[i] = binario.charCodeAt(i);
      window.__rosettaMicCheckBuffer = await contexto.decodeAudioData(bytes.buffer.slice(0));
      return true;
    } catch (e) {
      return false;
    }
  };

  window.__rosettaMicNoise = null;
  window.__rosettaStartMicNoise = () => {
    if (!state.context || !state.destination || window.__rosettaMicNoise) return false;

    if (window.__rosettaMicCheckBuffer) {
      const fuente = state.context.createBufferSource();
      fuente.buffer = window.__rosettaMicCheckBuffer;
      fuente.loop = true;
      fuente.connect(state.destination);
      fuente.start();
      window.__rosettaMicNoise = { oscilador: fuente, volumen: fuente };
      return true;
    }

    const oscilador = state.context.createOscillator();
    const volumen = state.context.createGain();
    oscilador.type = "sine";
    oscilador.frequency.value = 220;
    volumen.gain.value = 0.25;
    oscilador.connect(volumen);
    volumen.connect(state.destination);
    oscilador.start();
    window.__rosettaMicNoise = { oscilador, volumen };
    return true;
  };
  window.__rosettaStopMicNoise = () => {
    const activo = window.__rosettaMicNoise;
    if (!activo) return false;
    try { activo.oscilador.stop(); } catch (e) {}
    try { activo.volumen.disconnect(); } catch (e) {}
    window.__rosettaMicNoise = null;
    return true;
  };

  window.__rosettaDismissMicCheck = () => {
    for (const nodo of document.querySelectorAll("div, span, button")) {
      if (nodo.children.length) continue;
      const texto = (nodo.textContent || "").trim();
      // "Volver a intentar" aparece cuando la comprobación falló: hay que
      // pulsarlo también, ya con la señal sonando.
      if (!/^(comenzar|start|volver a intentar|try again|retry)$/i.test(texto)) continue;
      const objetivo = nodo.closest("[data-qa], button") || nodo;
      window.__rosettaStartMicNoise();
      emitirClic(objetivo);
      emitirClic(nodo);
      window.__rosettaMicCheckDismissed = true;
      // La señal se queda un rato: la comprobación dura unos segundos.
      clearTimeout(window.__rosettaNoiseTimer);
      window.__rosettaNoiseTimer = setTimeout(
        () => window.__rosettaStopMicNoise(), 30000
      );
      return true;
    }
    return false;
  };

  window.__rosettaMicCheckDismissed = false;
  const vigilante = new MutationObserver(() => {
    try { window.__rosettaDismissMicCheck(); } catch (e) {}
  });
  const arrancarVigilante = () => {
    if (document.documentElement) {
      vigilante.observe(document.documentElement, { childList: true, subtree: true });
    }
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arrancarVigilante);
  } else {
    arrancarVigilante();
  }

  window.__rosettaFeedMicrophone = async (encodedAudio) => {
    if (!state.context || !state.destination) {
      throw new Error("virtual microphone is not ready");
    }
    const binary = atob(encodedAudio);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const buffer = await state.context.decodeAudioData(bytes.buffer.slice(0));
    const source = state.context.createBufferSource();
    source.buffer = buffer;
    source.connect(state.destination);
    window.__rosettaMicPlaybackDone = false;
    source.onended = () => { window.__rosettaMicPlaybackDone = true; };
    // Give the recognizer a short lead-in after it receives the MediaStream.
    source.start(state.context.currentTime + 0.35);
    return buffer.duration + 0.35;
  };
})();
"""

_REFERENCE_AUDIO_CAPTURE_SCRIPT = r"""
(() => {
  if (window.__rosettaReferenceCaptureInstalled) return;
  window.__rosettaReferenceCaptureInstalled = true;
  window.__rosettaReferenceAudio = null;
  window.__rosettaReferenceAudioUrl = null;

  const encode = (buffer) => {
    const bytes = new Uint8Array(buffer);
    const chunkSize = 0x8000;
    let binary = "";
    for (let offset = 0; offset < bytes.length; offset += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
    }
    return btoa(binary);
  };

  // Cada audio decodificado se recuerda, no solo los de mientras capturamos.
  // El reproductor decodifica al cargar el paso y luego reproduce el buffer ya
  // cacheado, así que enganchar decodeAudioData solo durante la captura no veía
  // nada: para cuando pulsamos el altavoz ya no se decodifica nada nuevo.
  const bytesPorBuffer = new WeakMap();

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (AudioContextClass && AudioContextClass.prototype.decodeAudioData) {
    const originalDecode = AudioContextClass.prototype.decodeAudioData;
    AudioContextClass.prototype.decodeAudioData = function(arrayBuffer, ...args) {
      let copia = null;
      try {
        if (arrayBuffer.byteLength > 1000 && arrayBuffer.byteLength < 5000000) {
          // La copia va antes: decodeAudioData desprende el ArrayBuffer.
          copia = encode(arrayBuffer.slice(0));
        }
      } catch (e) { copia = null; }

      const resultado = originalDecode.call(this, arrayBuffer, ...args);
      if (copia && resultado && typeof resultado.then === "function") {
        resultado.then((buffer) => {
          try { bytesPorBuffer.set(buffer, copia); } catch (e) {}
        });
      }
      return resultado;
    };
  }

  // Las muestras del buffer que suena, serializadas a WAV. Es lo único que no
  // depende de nada externo: la URL de la media va firmada y devuelve 500 desde
  // fuera, y el descifrado ocurre en un worker donde estos ganchos no llegan.
  // El AudioBuffer, en cambio, ya está descifrado y en el hilo principal.
  const bufferAWav = (buffer) => {
    const canales = buffer.numberOfChannels;
    const tasa = buffer.sampleRate;
    const muestras = buffer.length;
    const bloque = canales * 2;
    const total = 44 + muestras * bloque;
    const datos = new ArrayBuffer(total);
    const vista = new DataView(datos);
    let pos = 0;
    const texto = (s) => { for (let i = 0; i < s.length; i++) vista.setUint8(pos++, s.charCodeAt(i)); };
    const u32 = (v) => { vista.setUint32(pos, v, true); pos += 4; };
    const u16 = (v) => { vista.setUint16(pos, v, true); pos += 2; };

    texto("RIFF"); u32(total - 8); texto("WAVE");
    texto("fmt "); u32(16); u16(1); u16(canales);
    u32(tasa); u32(tasa * bloque); u16(bloque); u16(16);
    texto("data"); u32(muestras * bloque);

    const pistas = [];
    for (let c = 0; c < canales; c++) pistas.push(buffer.getChannelData(c));
    for (let i = 0; i < muestras; i++) {
      for (let c = 0; c < canales; c++) {
        const v = Math.max(-1, Math.min(1, pistas[c][i]));
        vista.setInt16(pos, v < 0 ? v * 0x8000 : v * 0x7fff, true);
        pos += 2;
      }
    }
    return encode(datos);
  };

  if (window.AudioBufferSourceNode && AudioBufferSourceNode.prototype.start) {
    const originalStart = AudioBufferSourceNode.prototype.start;
    AudioBufferSourceNode.prototype.start = function(...args) {
      try {
        if (this.buffer && this.buffer.length > 0) {
          const bytes = bytesPorBuffer.get(this.buffer) || bufferAWav(this.buffer);
          window.__rosettaLastPlayedAudio = bytes;
          // Este nunca se reinicia: es la red de seguridad cuando el altavoz
          // de la respuesta no suena. Sigue siendo voz, que es lo que el
          // reconocedor necesita para dar un resultado.
          window.__rosettaAnyPlayedAudio = bytes;
          if (window.__rosettaCaptureReference === true) {
            window.__rosettaReferenceAudio = bytes;
          }
        }
      } catch (e) {}
      return originalStart.apply(this, args);
    };
  }

  // El reconocedor tarda segundos en cargar su modelo y lo anuncia por consola.
  // Pulsar antes de eso es lo que hacía que el altavoz "no sonara" en unas
  // corridas sí y en otras no.
  window.__rosettaSreReady = false;
  const originalLog = console.log;
  console.log = function(...args) {
    try {
      const texto = args.filter((a) => typeof a === "string").join(" ");
      if (texto.indexOf("done loading speech model") !== -1) {
        window.__rosettaSreReady = true;
      }
    } catch (e) {}
    return originalLog.apply(this, args);
  };

  const originalPlay = HTMLMediaElement.prototype.play;
  HTMLMediaElement.prototype.play = function(...args) {
    if (window.__rosettaCaptureReference === true) {
      const source = this.currentSrc || this.src;
      if (source) window.__rosettaReferenceAudioUrl = source;
    }
    return originalPlay.apply(this, args);
  };
})();
"""


class PlaywrightFluencySpeechPage(FluencySpeechPort, LoggingMixin):
    def __init__(
        self,
        page: Page,
        timeout_ms: int = 90_000,
        probe_timeout_ms: int = 15_000,
        trace_dir=None,
    ) -> None:
        self.page = page
        self.timeout_ms = timeout_ms
        # Con traza, una actividad fallida deja un .zip con capturas, DOM y la
        # lista de acciones: es la única forma de ver qué hacía el reproductor
        # cuando la corrida va headless dentro de un contenedor.
        self.trace_dir = trace_dir
        # Descubrir que una actividad no tiene micrófono no puede costar lo
        # mismo que esperar a que cargue una que sí lo tiene. Con el timeout
        # largo, un tipo mal enrutado se comía 90 s por actividad.
        self.probe_timeout_ms = probe_timeout_ms

    async def complete_activity(
        self,
        *,
        course_title: str,
        lesson_title: str,
        activity_id: str,
        expected_steps: int,
    ) -> bool:
        """Completa la conversación, grabando la sesión si se pidió traza."""
        tracing = await self._start_trace()
        completed = False
        try:
            completed = await self._complete_activity(
                course_title=course_title,
                lesson_title=lesson_title,
                activity_id=activity_id,
                expected_steps=expected_steps,
            )
            return completed
        finally:
            await self._stop_trace(tracing, activity_id, completed)

    async def _start_trace(self) -> bool:
        if not self.trace_dir:
            return False
        try:
            await self.page.context.tracing.start(screenshots=True, snapshots=True)
            return True
        except Exception as error:  # noqa: BLE001 - grabar es opcional
            self.logger.debug("  No se pudo iniciar la traza: %s", error)
            return False

    async def _stop_trace(self, tracing: bool, activity_id: str, completed: bool) -> None:
        """Guarda la traza solo si la actividad falló; si salió bien, se tira.

        Una traza pesa megas y una corrida toca decenas de actividades: guardar
        las que funcionaron llenaría el disco con lo que nadie va a mirar.
        """
        if not tracing:
            return
        try:
            if completed:
                await self.page.context.tracing.stop()
                return
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            destination = self.trace_dir / f"speech_trace_{activity_id[:8]}.zip"
            await self.page.context.tracing.stop(path=str(destination))
            self.logger.error(
                "  Traza de la actividad fallida en %s "
                "(ábrela con: uv run playwright show-trace %s)",
                destination,
                destination,
            )
        except Exception as error:  # noqa: BLE001 - grabar es opcional
            self.logger.debug("  No se pudo guardar la traza: %s", error)

    async def _complete_activity(
        self,
        *,
        course_title: str,
        lesson_title: str,
        activity_id: str,
        expected_steps: int,
    ) -> bool:
        try:
            await self.page.context.grant_permissions(
                ["microphone"], origin=LEARN_ORIGIN
            )
            await self.page.add_init_script(_VIRTUAL_MIC_SCRIPT)
            await self.page.add_init_script(_REFERENCE_AUDIO_CAPTURE_SCRIPT)
            await self._open_lesson(course_title, lesson_title)

            complete_marker = self.page.locator(
                f'[data-qa="activity_{activity_id}_correctly_completed"], '
                f'[data-qa="activity_{activity_id}_completed"]'
            )
            if await complete_marker.count():
                self.logger.info("  Speech activity already complete in lesson map")
                return True

            activity = self.page.get_by_test_id(f"activity_{activity_id}")
            await activity.wait_for(state="visible", timeout=self.timeout_ms)
            # The horizontal activity map places a transparent drag layer above
            # its items. Dispatching the click to the known data-qa target is the
            # same user action without relying on coordinates.
            await activity.click(force=True)
            try:
                await self.page.get_by_test_id("SpeechButton").wait_for(
                    state="visible", timeout=self.probe_timeout_ms
                )
            except PlaywrightTimeoutError:
                self.logger.error(
                    "  Esta actividad no tiene botón de micrófono: la ruta de voz "
                    "no le sirve (¿un tipo mal enrutado?)"
                )
                return False
            await self.page.evaluate(_VIRTUAL_MIC_SCRIPT)
            await self.page.evaluate(_REFERENCE_AUDIO_CAPTURE_SCRIPT)
            await self._load_mic_check_audio()
            await self._dismiss_microphone_check()

            for step_number in range(1, max(1, expected_steps) + 1):
                if not await self._complete_visible_step(step_number):
                    return False

                if step_number < expected_steps:
                    await self.page.get_by_test_id("SpeechButton").wait_for(
                        state="visible", timeout=self.timeout_ms
                    )

            return True
        except PlaywrightTimeoutError as exc:
            self.logger.error("  Speech browser flow timed out: %s", exc)
            return False
        except Exception as exc:  # noqa: BLE001 - keep the remaining run alive
            self.logger.error("  Speech browser flow failed: %s", exc)
            return False

    async def _open_lesson(self, course_title: str, lesson_title: str) -> None:
        await self.page.goto(LEARN_ORIGIN)
        courses = self.page.get_by_test_id("CourseDisplayerDiv")
        await courses.first.wait_for(state="visible", timeout=self.timeout_ms)

        course = await self._single_card(courses, course_title, "curso")
        await course.get_by_test_id("LaunchCourseButton").click()

        lessons = self.page.get_by_test_id("LessonDisplayer")
        await lessons.first.wait_for(state="visible", timeout=self.timeout_ms)
        lesson = await self._single_card(lessons, lesson_title, "lección")
        await lesson.get_by_test_id("LaunchButton").click()
        await self.page.get_by_test_id("ActivityMapList").wait_for(
            state="visible", timeout=self.timeout_ms
        )

    async def _single_card(self, cards: Any, title: str, kind: str) -> Any:
        """La tarjeta que toca. Varias coincidencias no son un fallo.

        Títulos como "Registration" se repiten entre cursos, y exigir una sola
        coincidencia hacía fracasar la actividad sin haberlo intentado. Cero
        coincidencias sí es un fallo: no hay dónde entrar.
        """
        matching = cards.filter(has_text=title)
        found = await matching.count()
        if found == 0:
            raise RuntimeError(f"no aparece ninguna tarjeta de {kind}: {title}")
        if found > 1:
            self.logger.warning(
                "  %d tarjetas de %s se llaman %r; se abre la primera",
                found,
                kind,
                title,
            )
        return matching.first

    async def _complete_visible_step(self, step_number: int) -> bool:
        prompt = self.page.get_by_test_id("PromptText")
        previous_prompt = (await prompt.text_content() or "").strip()
        choices = self.page.get_by_test_id("ChoiceButton")
        if await choices.count() == 0:
            self.logger.error("  Speech step %d has no choices", step_number)
            return False

        # El modal de micrófono puede aparecer al entrar en el paso, no solo al
        # abrir la actividad: se intenta cerrar en cada uno.
        await self._dismiss_microphone_check()
        choice = choices.first
        audio = await self._capture_choice_audio(choice)
        await self._wait_for_silence()
        if not await self._select_choice(choice):
            self.logger.error(
                "  El paso %d no llegó a seleccionar ninguna respuesta", step_number
            )
            await self._report_button_state()
            return False

        await self.page.evaluate(
            "() => { window.__rosettaMicReady = false; "
            "window.__rosettaMicPlaybackDone = false; }"
        )
        await self._click_speech_button()
        await self._wait(
            "() => window.__rosettaMicReady === true",
            "que el reproductor pida el micrófono (getUserMedia)",
        )
        await self.page.evaluate(
            "audio => window.__rosettaFeedMicrophone(audio)",
            base64.b64encode(audio).decode("ascii"),
        )
        await self._wait(
            "() => window.__rosettaMicPlaybackDone === true",
            "que termine de sonar el audio inyectado en el micrófono",
        )

        submit = self.page.get_by_test_id("SubmitButton")
        await self._wait(
            "() => { const e = document.querySelector('[data-qa=SubmitButton]'); "
            "return e && !/^(skip|omitir)$/i.test((e.textContent || '').trim()); }",
            "que el botón de enviar deje de decir Omitir",
        )
        await submit.click()
        await self._wait(
            "oldPrompt => { const e = document.querySelector('[data-qa=PromptText]'); "
            "return !e || (e.textContent || '').trim() !== oldPrompt; }",
            "que el reproductor pase al siguiente paso",
            previous_prompt,
        )
        return True

    async def _wait(self, expression: str, description: str, arg: Any = None) -> None:
        """Espera una condición del reproductor diciendo cuál es.

        Cinco esperas distintas daban el mismo "Page.wait_for_function: Timeout
        90000ms exceeded", que no permite arreglar nada: no se sabe si el botón
        no se habilitó, si el micrófono no arrancó o si el audio no sonó. Al
        fallar deja además una captura, que es lo único que enseña en qué
        pantalla se quedó el reproductor.
        """
        try:
            if arg is None:
                await self.page.wait_for_function(expression, timeout=self.timeout_ms)
            else:
                await self.page.wait_for_function(
                    expression, arg, timeout=self.timeout_ms
                )
        except PlaywrightTimeoutError:
            self.logger.error("  Se agotó la espera de: %s", description)
            await self._dump_screenshot(description)
            raise

    async def _dump_screenshot(self, description: str) -> None:
        try:
            from rosseta_stone_script_a.infrastructure.core import get_base_dir

            folder = get_base_dir() / "logs" / "diagnostics"
            folder.mkdir(parents=True, exist_ok=True)
            slug = "".join(c if c.isalnum() else "_" for c in description)[:60]
            destination = folder / f"speech_{slug}.png"
            await self.page.screenshot(path=str(destination))
            self.logger.info("  Captura del reproductor en %s", destination)
        except Exception as error:  # noqa: BLE001 - diagnosticar no puede fallar más
            self.logger.debug("  No se pudo guardar la captura: %s", error)

    async def _reference_audio_bytes(self, captured: dict) -> bytes:
        """Los bytes del audio, del sitio donde de verdad se pueden conseguir.

        Por orden: lo que decodificó el reproductor (siempre lo mejor), luego
        una descarga hecha **dentro** de la página, y solo al final el contexto
        de peticiones. Bajar la URL por fuera devolvía 500: esa media va firmada
        para la sesión de la página, y una URL ``blob:`` ni siquiera existe
        fuera de ella.
        """
        codificado = captured.get("audio")
        if codificado:
            return base64.b64decode(codificado)

        # Los bytes pueden llegar con un instante de retraso: el reproductor
        # arranca la fuente y decodifica justo después.
        codificado = await self._wait_for_decoded_bytes()
        if codificado:
            return base64.b64decode(codificado)

        url = captured.get("url") or await self._media_element_src()
        if not url:
            return b""

        desde_la_pagina = await self._download_in_page(url)
        if desde_la_pagina:
            return desde_la_pagina

        try:
            respuesta = await self.page.request.get(url)
            if respuesta.ok:
                return await respuesta.body()
            self.logger.warning(
                "  La descarga del audio respondió %s", respuesta.status
            )
        except Exception as error:  # noqa: BLE001 - ya no quedan vías
            self.logger.warning("  No se pudo descargar el audio: %s", error)
        return b""

    async def _wait_for_decoded_bytes(self) -> str:
        """Da un margen corto a que aparezcan los bytes ya decodificados."""
        try:
            await self.page.wait_for_function(
                "() => Boolean(window.__rosettaReferenceAudio || "
                "window.__rosettaLastPlayedAudio)",
                timeout=5_000,
            )
        except PlaywrightTimeoutError:
            return ""
        return await self.page.evaluate(
            "() => window.__rosettaReferenceAudio || window.__rosettaLastPlayedAudio"
        )

    async def _media_element_src(self) -> str:
        """La media que el reproductor tenga cargada, preguntándole al DOM.

        Último recurso cuando los ganchos no vieron nada: si el audio venía de
        un ``<audio>``, su ``currentSrc`` sigue ahí aunque nadie lo capturara.
        """
        try:
            return await self.page.evaluate(
                "() => { for (const a of document.querySelectorAll('audio, video')) "
                "{ if (a.currentSrc || a.src) return a.currentSrc || a.src; } "
                "return ''; }"
            )
        except Exception:  # noqa: BLE001 - preguntar no puede fallar la corrida
            return ""

    async def _download_in_page(self, url: str) -> bytes:
        """Descarga la media con las credenciales de la propia página."""
        try:
            codificado = await self.page.evaluate(
                """async (url) => {
                    const respuesta = await fetch(url, { credentials: 'include' });
                    if (!respuesta.ok) return null;
                    const datos = new Uint8Array(await respuesta.arrayBuffer());
                    let binario = "";
                    const trozo = 0x8000;
                    for (let i = 0; i < datos.length; i += trozo) {
                        binario += String.fromCharCode(...datos.subarray(i, i + trozo));
                    }
                    return btoa(binario);
                }""",
                url,
            )
        except Exception as error:  # noqa: BLE001 - queda el contexto de peticiones
            self.logger.debug("  La descarga dentro de la página falló: %s", error)
            return b""
        return base64.b64decode(codificado) if codificado else b""

    # Reproducir primero el audio del enunciado se probó y **empeoró las
    # cosas**: con él, el altavoz de las respuestas dejaba de responder (dos
    # corridas seguidas sin capturar nada, cuando las dos anteriores capturaban
    # a la primera). El reproductor parece quedarse ocupado con ese audio. Si
    # alguna vez hace falta oír el enunciado, hay que comprobar antes que las
    # respuestas siguen sonando después.

    async def _wait_for_silence(self) -> None:
        """Espera a que el reproductor deje de sonar. No falla si sigue."""
        try:
            await self.page.wait_for_function(
                "() => !document.querySelector('[data-qa=audio_playing]')",
                timeout=self.probe_timeout_ms,
            )
        except PlaywrightTimeoutError:
            self.logger.debug("  El reproductor sigue con audio; se continúa")

    async def _play_reference_audio(self, listen: Any) -> bool:
        """Hace sonar la respuesta, comprobando que de verdad suena."""
        intentos = (
            ("el altavoz", lambda: listen.first.click(force=True, timeout=self.probe_timeout_ms)),
            ("el altavoz por DOM", lambda: listen.first.evaluate("el => el.click()")),
            ("el icono del altavoz", lambda: listen.first.get_by_test_id("SpeakerIcon").first.click(force=True, timeout=self.probe_timeout_ms)),
        )
        await self._wait_for_recognizer()
        # Dos pasadas: la primera puede caer mientras el reproductor todavía se
        # está montando, y entonces ninguna de las tres vías suena.
        for pasada in (1, 2):
            for descripcion, intento in intentos:
                try:
                    await intento()
                except Exception as error:  # noqa: BLE001 - se prueba el siguiente
                    self.logger.debug("  No se pudo pulsar %s: %s", descripcion, error)
                    continue
                if await self._reference_audio_captured():
                    self.logger.info(
                        "  Audio de referencia capturado con %s%s",
                        descripcion,
                        "" if pasada == 1 else " (segunda pasada)",
                    )
                    return True
        return False

    async def _load_mic_check_audio(self) -> None:
        """Carga la grabación de la comprobación de micrófono, si la hay.

        La prueba pide decir "1, 2, 3, 4, 5" y escucha. Una voz de verdad la
        pasa; un tono puede que sí, puede que no. El archivo se busca en
        ``<ROSETTA_HOME>/audio/mic_check.(wav|mp3|m4a|ogg)`` — si no está, se
        usa el tono y no pasa nada.
        """
        from rosseta_stone_script_a.infrastructure.core import get_base_dir

        carpeta = get_base_dir() / "audio"
        for nombre in ("mic_check.wav", "mic_check.mp3", "mic_check.m4a", "mic_check.ogg"):
            archivo = carpeta / nombre
            if not archivo.exists():
                continue
            try:
                codificado = base64.b64encode(archivo.read_bytes()).decode("ascii")
                listo = await self.page.evaluate(
                    "audio => window.__rosettaPrepareMicCheckAudio(audio)", codificado
                )
                self.logger.info(
                    "  Grabación para la comprobación de micrófono: %s (%s)",
                    archivo.name,
                    "decodificada" if listo else "no se pudo decodificar",
                )
            except Exception as error:  # noqa: BLE001 - el tono sigue disponible
                self.logger.info("  No se pudo cargar %s: %s", archivo.name, error)
            return
        self.logger.debug("  Sin grabación propia: la comprobación usará un tono")

    async def _dismiss_microphone_check(self) -> None:
        """Cierra el modal de "Comprobación de micrófono".

        Es lo que bloqueaba la actividad entera: una capa por encima de todo
        con un desplegable de dispositivos y un botón *Comenzar*. Detrás de ella
        ningún clic llegaba a las respuestas y el micrófono seguía deshabilitado
        — durante once corridas pareció un problema de selectores.

        En un contenedor el desplegable sale vacío, así que además se elige el
        primer dispositivo que haya (el falso que inyecta el navegador o el que
        añade el guion del micrófono virtual).
        """
        etiqueta = re.compile(r"^\s*(comenzar|start|continuar|continue)\s*$", re.I)
        try:
            # El desplegable primero: el botón puede depender de que haya
            # dispositivo elegido. Va en su propio try — si esto falla (el
            # select puede no ser interactuable), lo que no puede es impedir
            # que se pulse el botón, que es lo importante.
            try:
                selector = self.page.locator("select")
                if await selector.count():
                    opciones = await selector.first.locator("option").count()
                    if opciones:
                        await selector.first.select_option(index=opciones - 1)
            except Exception as error:  # noqa: BLE001 - el botón sigue en pie
                self.logger.info("  No se pudo elegir micrófono: %s", error)

            # "Comenzar" no es un <button>: en este reproductor los controles
            # son divs con data-qa, así que buscarlo por rol no encuentra nada
            # y el modal se quedaba abierto en silencio.
            candidatos = (
                ("por rol", self.page.get_by_role("button", name=etiqueta)),
                ("por data-qa", self.page.get_by_test_id("PromptButton")),
                ("por texto", self.page.get_by_text(etiqueta)),
            )
            # El vigilante inyectado ya lo habrá cerrado casi siempre; esto es
            # el segundo intento desde fuera, por si acaso.
            cerrado = await self.page.evaluate(
                "() => Boolean(window.__rosettaDismissMicCheck "
                "&& window.__rosettaDismissMicCheck())"
            )
            if cerrado:
                self.logger.info("  Comprobación de micrófono aceptada (vigilante)")
                return

            encontrados = []
            for descripcion, candidato in candidatos:
                cuantos = await candidato.count()
                encontrados.append("%s=%d" % (descripcion, cuantos))
                if not cuantos:
                    continue
                await candidato.first.click(force=True, timeout=self.probe_timeout_ms)
                self.logger.info(
                    "  Comprobación de micrófono aceptada (%s)", descripcion
                )
                return
            # A nivel debug esto era invisible y el modal se quedaba abierto sin
            # que nada lo dijera: dos corridas perdidas por no ver esta línea.
            self.logger.info(
                "  No se encontró el botón del modal de micrófono (%s)",
                ", ".join(encontrados),
            )
        except Exception as error:  # noqa: BLE001 - puede no estar
            self.logger.debug("  No se pudo cerrar el modal de micrófono: %s", error)

    async def _wait_for_recognizer(self) -> None:
        """Espera a que el reconocedor termine de cargar su modelo.

        Lo anuncia por consola y el guion de captura lo apunta. Es de mejor
        esfuerzo: si la señal no llega, se sigue igual — pero pulsar antes de
        tiempo es lo que hacía que el altavoz no sonara en unas corridas sí y
        en otras no.
        """
        try:
            await self.page.wait_for_function(
                "() => window.__rosettaSreReady === true",
                timeout=self.probe_timeout_ms,
            )
        except PlaywrightTimeoutError:
            self.logger.debug("  El reconocedor no avisó de estar listo; se continúa")

    async def _reference_audio_captured(self) -> bool:
        """¿Empezó a sonar la respuesta?

        Vale cualquier señal: que uno de nuestros ganchos lo pillara, o que el
        propio reproductor muestre ``audio_playing``. Exigir solo lo primero
        daba falsos negativos — el clic funcionaba, sonaba, y aun así lo
        dábamos por fallido porque el audio venía de un buffer que nuestros
        ganchos no habían visto decodificar.
        """
        try:
            await self.page.wait_for_function(
                "() => Boolean(window.__rosettaReferenceAudio || "
                "window.__rosettaReferenceAudioUrl || window.__rosettaLastPlayedAudio "
                "|| document.querySelector('[data-qa=audio_playing]'))",
                timeout=8_000,
            )
            return True
        except PlaywrightTimeoutError:
            return False

    async def _select_choice(self, choice: Any) -> bool:
        """Marca la respuesta y comprueba que el reproductor se ha enterado.

        Las respuestas son radios (``ChoiceButton_1/2/3``) y el micrófono no se
        habilita hasta que hay una marcada: en la traza de la actividad fallida
        el botón de enviar seguía diciendo "Omitir", que es como se ve "no has
        elegido nada". El clic normal cae en el centro de la ficha, donde está
        el altavoz, así que se apunta al texto y, si no cuela, se despacha el
        clic por DOM sobre la ficha entera.
        """
        intentos = (
            ("el texto de la respuesta", self._click_choice_text),
            ("la ficha entera", self._click_choice_box),
            ("un clic despachado por DOM", self._dispatch_choice_click),
            ("la secuencia completa de puntero", self._dispatch_pointer_sequence),
            ("la secuencia sobre todo el subárbol", self._dispatch_on_subtree),
        )
        for descripcion, intento in intentos:
            try:
                await intento(choice)
            except Exception as error:  # noqa: BLE001 - se prueba el siguiente
                self.logger.debug("  No se pudo pulsar %s: %s", descripcion, error)
                continue
            if await self._choice_registered():
                self.logger.info("  Respuesta marcada pulsando %s", descripcion)
                return True
        return False

    async def _choice_registered(self) -> bool:
        """¿Se ha enterado el reproductor de que hemos elegido?

        Antes esto preguntaba solo si se había habilitado el micrófono, y eso
        da por fallida una selección que sí ocurrió cuando el micrófono depende
        de otra cosa. Las tres señales que sirven:

        - el botón de enviar deja de decir "Omitir" (con nada elegido dice eso),
        - hay algo marcado (``aria-checked`` o un radio real),
        - el micrófono se habilita.
        """
        try:
            await self.page.wait_for_function(
                """() => {
                    const enviar = document.querySelector('[data-qa=SubmitButton]');
                    const texto = enviar
                        ? (enviar.getAttribute('data-qa-button-text')
                           || enviar.textContent || '').trim()
                        : '';
                    const yaNoOmite = Boolean(texto) && !/^(skip|omitir)$/i.test(texto);
                    const marcado = document.querySelector(
                        '[aria-checked=true], input[type=radio]:checked'
                    );
                    const mic = document.querySelector('[data-qa=SpeechButton]');
                    const micListo = mic && !mic.hasAttribute('disabled')
                        && mic.getAttribute('aria-disabled') !== 'true';
                    return Boolean(yaNoOmite || marcado || micListo);
                }""",
                timeout=5_000,
            )
            return True
        except PlaywrightTimeoutError:
            return False

    async def _click_choice_text(self, choice: Any) -> None:
        texto = choice.get_by_test_id("ChoiceText")
        if await texto.count() == 0:
            raise RuntimeError("la respuesta no tiene texto que pulsar")
        await texto.first.click(force=True, timeout=self.probe_timeout_ms)

    async def _click_choice_box(self, choice: Any) -> None:
        await choice.click(force=True, timeout=self.probe_timeout_ms)

    async def _dispatch_choice_click(self, choice: Any) -> None:
        await choice.evaluate("el => el.click()")

    async def _dispatch_pointer_sequence(self, choice: Any) -> None:
        """Puntero completo sobre la ficha y sus hijos.

        React escucha ``pointerdown``/``mousedown`` en componentes propios, no
        siempre el ``click`` del DOM, y en las 72 instantáneas de la traza la
        clase del radio no cambió ni una vez: los clics anteriores no llegaban
        al componente. Se emite la secuencia entera, y también sobre el primer
        hijo por si el manejador vive ahí.
        """
        await choice.evaluate(
            """el => {
                const emitir = (nodo) => {
                    for (const tipo of ['pointerdown', 'mousedown', 'mouseup', 'click']) {
                        const Evento = tipo.startsWith('pointer') && window.PointerEvent
                            ? PointerEvent : MouseEvent;
                        nodo.dispatchEvent(new Evento(tipo, {
                            bubbles: true, cancelable: true, composed: true,
                            button: 0, buttons: 1,
                        }));
                    }
                };
                emitir(el);
                if (el.firstElementChild) emitir(el.firstElementChild);
            }"""
        )

    async def _dispatch_on_subtree(self, choice: Any) -> None:
        """La secuencia de puntero sobre cada nodo de la respuesta.

        En la traza, la clase del radio no cambia nunca mientras
        ``audio_playing`` se enciende una vez por intento: los clics acaban en
        el altavoz, que es hijo de la misma ficha. No se sabe qué nodo escucha
        de verdad, así que se recorren todos — menos el altavoz y su icono,
        que son precisamente los que hacen sonar el audio en vez de elegir.
        """
        await choice.evaluate(
            """el => {
                const emitir = (nodo) => {
                    for (const tipo of ['pointerdown', 'mousedown', 'mouseup', 'click']) {
                        const Evento = tipo.startsWith('pointer') && window.PointerEvent
                            ? PointerEvent : MouseEvent;
                        nodo.dispatchEvent(new Evento(tipo, {
                            bubbles: true, cancelable: true, composed: true,
                            button: 0, buttons: 1,
                        }));
                    }
                };
                const esAltavoz = (nodo) => Boolean(
                    nodo.closest('[data-qa=ListenButton], [data-qa=audio_paused], [data-qa=audio_playing]')
                );
                emitir(el);
                for (const nodo of el.querySelectorAll('*')) {
                    if (!esAltavoz(nodo)) emitir(nodo);
                }
                if (el.parentElement) emitir(el.parentElement);
            }"""
        )

    async def _speech_button_enabled(self) -> bool:
        """¿Se habilitó el micrófono? Se pregunta corto: es una comprobación."""
        try:
            await self.page.wait_for_function(
                "() => { const e = document.querySelector('[data-qa=SpeechButton]'); "
                "return e && !e.hasAttribute('disabled') "
                "&& e.getAttribute('aria-disabled') !== 'true'; }",
                timeout=5_000,
            )
            return True
        except PlaywrightTimeoutError:
            return False

    async def _click_speech_button(self) -> None:
        """Pulsa el micrófono cuando de verdad se puede pulsar.

        El reproductor deja el botón con ``disabled`` mientras suena el audio
        del diálogo, y encima pinta una capa que se traga el clic. Sin esperar a
        que se habilite, Playwright reintenta 60 veces contra el mismo overlay y
        muere a los 30 s. ``force`` remata: salta la comprobación de
        interceptación, que es lo que fallaba aunque el botón ya estuviera listo.
        """
        button = self.page.get_by_test_id("SpeechButton")
        await button.wait_for(state="visible", timeout=self.timeout_ms)

        # El reproductor mantiene el micrófono deshabilitado mientras suena
        # cualquier audio suyo — y el que suena es el nuestro: para capturar la
        # respuesta de referencia hay que pulsar el altavoz. En la traza de la
        # actividad fallida se ve `audio_playing` yendo y viniendo durante los
        # 90 s que pasamos esperando a que el botón se habilitara.
        await self._wait(
            "() => !document.querySelector('[data-qa=audio_playing]')",
            "que el reproductor deje de reproducir audio",
        )
        try:
            await self._wait(
                "() => { const e = document.querySelector('[data-qa=SpeechButton]'); "
                "return e && !e.hasAttribute('disabled') "
                "&& e.getAttribute('aria-disabled') !== 'true'; }",
                "que se habilite el botón de micrófono",
            )
        except PlaywrightTimeoutError:
            await self._report_button_state()
            raise
        await button.click(force=True, timeout=self.timeout_ms)

    async def _report_button_state(self) -> None:
        """Cómo estaba el botón cuando se agotó la espera.

        Sin esto, "no se habilitó" no distingue entre seguir con audio, estar
        tapado por un modal o que el reproductor cambiara el marcado.
        """
        try:
            estado = await self.page.evaluate(
                "() => { const e = document.querySelector('[data-qa=SpeechButton]'); "
                "return { existe: Boolean(e), html: e ? e.outerHTML.slice(0, 300) : null, "
                "audio: Boolean(document.querySelector('[data-qa=audio_playing]')) }; }"
            )
            self.logger.error(
                "  Estado del micrófono: audio sonando=%s | %s",
                estado.get("audio"),
                estado.get("html"),
            )
        except Exception as error:  # noqa: BLE001 - diagnosticar no puede fallar más
            self.logger.debug("  No se pudo leer el estado del botón: %s", error)

    async def _capture_choice_audio(self, choice: Any) -> bytes:
        listen = choice.get_by_test_id("ListenButton")
        if await listen.count() == 0:
            # Some player versions render the speaker as a sibling while keeping
            # the same order as ChoiceButton.
            listen = self.page.get_by_test_id("ListenButton").last

        await self.page.evaluate(
            "() => { window.__rosettaReferenceAudio = null; "
            "window.__rosettaReferenceAudioUrl = null; "
            "window.__rosettaLastPlayedAudio = null; "
            "window.__rosettaCaptureReference = true; }"
        )
        try:
            # Pulsar el altavoz falla de forma intermitente: la ficha lleva una
            # capa decorativa encima y el clic por coordenadas cae donde cae.
            # Se prueban varias formas y se comprueba que algo empezó a sonar,
            # en vez de esperar 90 s a un audio que nunca arrancó.
            if not await self._play_reference_audio(listen):
                # Que el altavoz no suene no puede seguir costando la corrida:
                # lo que el reconocedor necesita es *voz*, y el diálogo que
                # sonó al abrir el paso también lo es. Se avisa de que el audio
                # no es el de la respuesta elegida — puntuará peor, pero deja
                # ver por fin qué pasa en los pasos siguientes.
                self.logger.warning(
                    "  El altavoz de la respuesta no sonó; se usa el último "
                    "audio que reprodujo el reproductor"
                )
            captured = await self.page.evaluate(
                "() => ({ audio: window.__rosettaReferenceAudio "
                "|| window.__rosettaLastPlayedAudio "
                "|| window.__rosettaAnyPlayedAudio, "
                "url: window.__rosettaReferenceAudioUrl })"
            )
        finally:
            await self.page.evaluate(
                "() => { window.__rosettaCaptureReference = false; }"
            )

        body = await self._reference_audio_bytes(captured)
        if not body:
            raise RuntimeError("no se pudo obtener el audio de referencia")

        playing = self.page.locator('[data-qa="audio_playing"]')
        if await playing.count():
            await playing.wait_for(state="detached", timeout=self.timeout_ms)
        return body
