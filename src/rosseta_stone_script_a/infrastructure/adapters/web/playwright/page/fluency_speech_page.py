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
  // Cuántas veces ha pedido el micrófono la página. El reproductor lo pide una
  // sola vez —en la comprobación— y reutiliza ese MediaStream para toda la
  // actividad, así que "¿lo ha vuelto a pedir?" no sirve para saber si está
  // listo; esto permite distinguir una petición nueva de la reutilización.
  window.__rosettaMicRequests = 0;

  const devices = navigator.mediaDevices;
  const original = devices.getUserMedia.bind(devices);
  const state = { context: null, destination: null, bus: null };

  // Un solo "bus" de micrófono, creado una vez y conectado a cada destino que
  // entregue getUserMedia. Antes cada fuente se conectaba al destino de turno,
  // y el destino solo existe cuando la página ya ha pedido el micrófono: la
  // señal de la calibración arrancaba antes de esa petición, se conectaba a
  // nada, y el medidor se quedaba en una barra. Con el bus da igual el orden.
  const asegurarContexto = async () => {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!state.context) state.context = new AudioContextClass({ sampleRate: 48000 });
    if (!state.bus) state.bus = state.context.createGain();
    try { await state.context.resume(); } catch (e) {}
    return state.context;
  };

  devices.getUserMedia = async (constraints) => {
    if (!constraints || !constraints.audio) return original(constraints);
    await asegurarContexto();
    state.destination = state.context.createMediaStreamDestination();
    state.bus.connect(state.destination);
    window.__rosettaMicReady = true;
    window.__rosettaMicRequests = (window.__rosettaMicRequests || 0) + 1;
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
      const contexto = await asegurarContexto();
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
  // Arranca la señal sin esperar a que la página haya pedido el micrófono: va
  // al bus, y el bus se engancha solo al destino que se cree después.
  window.__rosettaStartMicNoise = () => {
    if (window.__rosettaMicNoise) return true;
    window.__rosettaMicNoise = "arrancando";
    asegurarContexto().then(() => {
      if (window.__rosettaMicNoise !== "arrancando") return;

      if (window.__rosettaMicCheckBuffer) {
        const fuente = state.context.createBufferSource();
        fuente.buffer = window.__rosettaMicCheckBuffer;
        fuente.loop = true;
        fuente.connect(state.bus);
        fuente.start();
        window.__rosettaMicNoise = { oscilador: fuente, volumen: fuente };
        return;
      }

      const oscilador = state.context.createOscillator();
      const volumen = state.context.createGain();
      oscilador.type = "sine";
      oscilador.frequency.value = 220;
      volumen.gain.value = 0.25;
      oscilador.connect(volumen);
      volumen.connect(state.bus);
      oscilador.start();
      window.__rosettaMicNoise = { oscilador, volumen };
    }).catch(() => { window.__rosettaMicNoise = null; });
    return true;
  };
  window.__rosettaStopMicNoise = () => {
    const activo = window.__rosettaMicNoise;
    if (!activo) return false;
    window.__rosettaMicNoise = null;
    if (activo === "arrancando") return true;
    try { activo.oscilador.stop(); } catch (e) {}
    try { activo.volumen.disconnect(); } catch (e) {}
    return true;
  };

  // La comprobación tiene dos caras y solo una tiene botón: primero elegir
  // dispositivo y pulsar *Comenzar*, y después "Comprobando el micrófono...",
  // que se queda escuchando sin nada que pulsar. Mirar solo el botón daba
  // "no se encontró el modal" mientras seguía tapando la pantalla entera
  // (va en `position: fixed` con `z-index: 7000`, así que ningún clic a las
  // respuestas llegaba).
  const ventanaCalibracion = () =>
    document.querySelector('[data-qa="CalibrationWindow"]');

  window.__rosettaMicCheckState = () => {
    const ventana = ventanaCalibracion();
    if (!ventana) return { presente: false };
    const medidor = ventana.querySelector('[data-qa="CalibrateMeter"]');
    return {
      presente: true,
      escuchando: Boolean(
        ventana.querySelector('[data-qa="mic_calibration_checking_microphone"]')
      ),
      barras: medidor ? medidor.querySelectorAll(".bar").length : 0,
      encendidas: medidor ? medidor.querySelectorAll(".lit").length : 0,
      senal: Boolean(window.__rosettaMicNoise),
      texto: (ventana.textContent || "").trim().slice(0, 120),
    };
  };

  window.__rosettaDismissMicCheck = () => {
    const ventana = ventanaCalibracion();
    // La señal primero: el botón arranca la escucha, y si para entonces no
    // suena nada la comprobación se agota antes de que nos dé tiempo.
    if (ventana) window.__rosettaStartMicNoise();
    const raiz = ventana || document;
    // "Continuar" solo se acepta dentro de la ventana de calibración: es el
    // botón del tercer diálogo, "Comprobación de micrófono exitosa · ¡Está
    // todo listo!", que se queda esperando y tapando la actividad aunque la
    // comprobación haya salido bien. Fuera de la ventana no se toca, que
    // "Continuar" es una palabra que sale en media plataforma.
    const etiquetas = ventana
      ? /^(comenzar|start|continuar|continue|volver a intentar|try again|retry)$/i
      : /^(comenzar|start|volver a intentar|try again|retry)$/i;
    for (const nodo of raiz.querySelectorAll("div, span, button")) {
      if (nodo.children.length) continue;
      const texto = (nodo.textContent || "").trim();
      // "Volver a intentar" aparece cuando la comprobación falló: hay que
      // pulsarlo también, ya con la señal sonando.
      if (!etiquetas.test(texto)) continue;
      const objetivo = nodo.closest("[data-qa], button") || nodo;
      emitirClic(objetivo);
      emitirClic(nodo);
      window.__rosettaMicCheckDismissed = true;
      return true;
    }
    return false;
  };

  window.__rosettaMicCheckDismissed = false;
  // Mientras la ventana esté, la señal suena; cuando se va, se calla. Antes lo
  // decidía un temporizador de 30 s que tanto podía cortar a mitad de la
  // comprobación como seguir sonando encima de la respuesta.
  const atenderCalibracion = () => {
    if (ventanaCalibracion()) {
      window.__rosettaDismissMicCheck();
    } else if (window.__rosettaMicNoise) {
      window.__rosettaStopMicNoise();
    }
  };
  const vigilante = new MutationObserver(() => {
    try { atenderCalibracion(); } catch (e) {}
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
    // El bucle de la calibración ("1, 2, 3, 4, 5") no puede seguir sonando por
    // encima de la respuesta: el reconocedor oiría las dos cosas mezcladas.
    window.__rosettaStopMicNoise();
    const binary = atob(encodedAudio);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const buffer = await state.context.decodeAudioData(bytes.buffer.slice(0));
    const source = state.context.createBufferSource();
    source.buffer = buffer;
    source.connect(state.bus);
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
        speech_attempts: int = 3,
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
        # Que el reconocedor no entienda una respuesta no es un fallo: a una
        # persona también le pasa, y el reproductor ofrece "Volver a intentar".
        self.speech_attempts = max(1, speech_attempts)
        # Ver _wait_for_recognizer: se rearma al empezar cada actividad.
        self._reconocedor_mudo = False

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
        self._reconocedor_mudo = False
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

            # El mapa pinta la misma actividad dos veces (medido en una
            # corrida real): sin ``.first`` esperarla es una violación de
            # modo estricto que tumba la actividad entera.
            activity = self.page.get_by_test_id(f"activity_{activity_id}").first
            await activity.wait_for(state="visible", timeout=self.timeout_ms)
            # The horizontal activity map places a transparent drag layer above
            # its items. Dispatching the click to the known data-qa target is the
            # same user action without relying on coordinates.
            await activity.click(force=True)

            modo = await self._input_mode()
            if modo == "desconocido":
                self.logger.error(
                    "  La actividad no enseñó ni micrófono ni respuestas: no hay "
                    "nada que contestar (¿un tipo mal enrutado?)"
                )
                return False

            if modo == "hablar":
                await self.page.evaluate(_VIRTUAL_MIC_SCRIPT)
                await self.page.evaluate(_REFERENCE_AUDIO_CAPTURE_SCRIPT)
                await self._load_mic_check_audio()
                await self._dismiss_microphone_check()
            else:
                self.logger.info(
                    "  Conversación sin reconocimiento: se responde eligiendo, "
                    "no hablando"
                )

            for step_number in range(1, max(1, expected_steps) + 1):
                resuelto = (
                    await self._complete_visible_step(step_number)
                    if modo == "hablar"
                    else await self._complete_visible_choice_step(step_number)
                )
                if not resuelto:
                    return False

                if step_number < expected_steps and not await self._another_step_starts(
                    step_number, modo
                ):
                    return True

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
        await course.get_by_test_id("LaunchCourseButton").first.click()

        lessons = self.page.get_by_test_id("LessonDisplayer")
        await lessons.first.wait_for(state="visible", timeout=self.timeout_ms)
        lesson = await self._single_card(lessons, lesson_title, "lección")
        await lesson.get_by_test_id("LaunchButton").first.click()
        await self.page.get_by_test_id("ActivityMapList").first.wait_for(
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
        prompt = self.page.get_by_test_id("PromptText").first
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
        # Marcar la respuesta ayuda, pero **no es obligatorio**: en esta
        # actividad se contesta hablando, y el reconocedor decide cuál de las
        # tres has dicho. Se comprobó en una corrida real — sin ninguna marcada,
        # el reproductor escuchó y contestó "Volver a intentar", que es un
        # veredicto, no un bloqueo. Tratarlo como error hundía el paso antes de
        # llegar a hablar, que es lo único que de verdad lo resuelve.
        if not await self._select_choice(choice, exhaustivo=False):
            self.logger.info(
                "  El paso %d no marcó ninguna respuesta; se contesta hablando",
                step_number,
            )

        if not await self._speak_until_accepted(audio, step_number):
            return False

        self.logger.info("  Paso %d resuelto; se pasa al siguiente", step_number)
        if not await self._advance_to_next_step(previous_prompt):
            self.logger.error(
                "  El paso %d quedó resuelto pero el reproductor no avanzó",
                step_number,
            )
            await self._dump_screenshot("sin_avanzar_de_paso")
            return False
        return True

    # Tras un clic, el reproductor cambia *algo* en menos de un segundo: o el
    # enunciado (avanzó) o el texto del botón (registró la pulsación). Cuatro
    # segundos son de sobra; lo que sobraba eran los quince que se esperaban
    # antes por no mirar el botón.
    _ADVANCE_PROBE_MS = 4_000

    async def _advance_to_next_step(self, previous_prompt: str) -> bool:
        """Pulsa hasta que el enunciado cambie, mirando qué pasa entre clics.

        Hacen falta **dos** pulsaciones por paso: la primera envía la respuesta
        y solo cambia el texto del botón; la segunda es la que avanza. Esperar
        únicamente al cambio de enunciado hacía que la primera agotara el
        timeout entero — 15 s por paso, en las dos rutas. Medido en las trazas:
        clic, 15 s en blanco, segundo clic, y el enunciado cambia al instante.

        (El docstring anterior culpaba al botón de llegar deshabilitado. No es
        eso: la comprobación de habilitado tarda 0,00 s antes del segundo clic.
        El primer clic no se pierde, gasta una transición distinta.)

        Se mira el enunciado **antes** de cada pulsación, así que en cuanto ha
        avanzado ya no se pulsa más. Eso es lo que impide el fallo peligroso:
        un clic de más caería sobre el "Omitir" del paso siguiente y lo saltaría
        sin contestarlo.
        """
        estado = (
            "() => { const p = document.querySelector('[data-qa=PromptText]'); "
            "const b = document.querySelector('[data-qa=SubmitButton]'); "
            "return { prompt: p ? (p.textContent || '').trim() : null, "
            "boton: b ? (b.getAttribute('data-qa-button-text') "
            "|| b.textContent || '').trim() : '', "
            "listo: Boolean(b) && !b.hasAttribute('disabled') "
            "&& b.getAttribute('aria-disabled') !== 'true' }; }"
        )
        boton = self.page.get_by_test_id("SubmitButton").first

        for _ in range(self.speech_attempts):
            antes = await self.page.evaluate(estado)
            # Ya estamos en el paso siguiente: pulsar ahora sería saltárselo.
            if antes["prompt"] is None or antes["prompt"] != previous_prompt:
                return True

            try:
                await self.page.wait_for_function(
                    "() => { const e = document.querySelector('[data-qa=SubmitButton]'); "
                    "return e && !e.hasAttribute('disabled') "
                    "&& e.getAttribute('aria-disabled') !== 'true'; }",
                    timeout=self._ADVANCE_PROBE_MS,
                )
            except PlaywrightTimeoutError:
                pass  # se intenta pulsar igual: el atributo puede no estar

            try:
                await boton.click(force=True, timeout=self.probe_timeout_ms)
            except Exception as error:  # noqa: BLE001 - queda otro intento
                self.logger.debug("  No se pudo pulsar el paso siguiente: %s", error)

            # Cualquiera de las dos señales sirve para seguir: el enunciado
            # cambió (hemos acabado) o el botón cambió (el clic entró, toca
            # pulsar otra vez). Solo si no se mueve nada se espera de verdad.
            movio = (
                "datos => { const p = document.querySelector('[data-qa=PromptText]'); "
                "const b = document.querySelector('[data-qa=SubmitButton]'); "
                "const prompt = p ? (p.textContent || '').trim() : null; "
                "const boton = b ? (b.getAttribute('data-qa-button-text') "
                "|| b.textContent || '').trim() : ''; "
                "return prompt === null || prompt !== datos.prompt "
                "|| boton !== datos.boton; }"
            )
            try:
                await self.page.wait_for_function(
                    movio, arg=antes, timeout=self._ADVANCE_PROBE_MS
                )
            except PlaywrightTimeoutError:
                # Nada se movió: puede que el reproductor siga ocupado. Esta es
                # la única espera que conserva la sonda larga.
                try:
                    await self.page.wait_for_function(
                        "oldPrompt => { const e = "
                        "document.querySelector('[data-qa=PromptText]'); "
                        "return !e || (e.textContent || '').trim() !== oldPrompt; }",
                        arg=previous_prompt,
                        timeout=self.probe_timeout_ms,
                    )
                    return True
                except PlaywrightTimeoutError:
                    continue

            despues = await self.page.evaluate(estado)
            if despues["prompt"] is None or despues["prompt"] != previous_prompt:
                return True
            # Solo cambió el botón: el clic entró y falta el que avanza.

        return False

    async def _speak_until_accepted(self, audio: bytes, step_number: int) -> bool:
        """Dice la respuesta hasta que el reproductor la dé por buena.

        Mientras el paso está sin resolver el botón de enviar solo tiene dos
        textos: **"Omitir"** (no ha oído nada) y **"Volver a intentar"** (ha
        oído y no ha entendido). Dar por buena "cualquier cosa que no sea
        Omitir" hacía pulsar *Volver a intentar*, que reinicia el paso — el
        reproductor volvía al principio y la espera del enunciado siguiente se
        agotaba a los 90 s sin que nada dijera por qué.
        """
        for intento in range(1, self.speech_attempts + 1):
            if intento > 1 and not await self._press_retry():
                return False

            peticiones = await self.page.evaluate(
                "() => { window.__rosettaMicPlaybackDone = false; "
                "return window.__rosettaMicRequests || 0; }"
            )
            await self._click_speech_button()
            # La comprobación de micrófono salta la primera vez que se usa el
            # micrófono de la actividad: se come esa pulsación y luego se queda
            # en su diálogo de "todo listo" tapándolo todo. Si ha aparecido, hay
            # que volver a pulsar cuando se ha ido.
            if await self._dismiss_microphone_check():
                await self._click_speech_button()
            await self._wait_for_microphone(peticiones)
            await self._wait_until_recording()
            await self.page.evaluate(
                "audio => window.__rosettaFeedMicrophone(audio)",
                base64.b64encode(audio).decode("ascii"),
            )
            await self._wait(
                "() => window.__rosettaMicPlaybackDone === true",
                "que termine de sonar el audio inyectado en el micrófono",
            )

            veredicto = await self._submit_verdict()
            if veredicto == "aceptada":
                return True
            self.logger.info(
                "  El reconocedor %s en el paso %d (intento %d de %d)",
                "no oyó nada" if veredicto == "sin respuesta" else "no lo entendió",
                step_number,
                intento,
                self.speech_attempts,
            )

        self.logger.error(
            "  El paso %d no logró que se aceptara la respuesta hablada", step_number
        )
        await self._dump_screenshot("respuesta_no_aceptada")
        return False

    async def _another_step_starts(
        self, step_number: int, modo: str = "hablar"
    ) -> bool:
        """¿Queda otro paso, o la conversación se acabó antes de la cuenta?

        ``expected_steps`` viene de la API y **no coincide con lo que pinta el
        reproductor**: una actividad que declaraba 13 tenía 10 enunciados. Al
        acabar el décimo se esperaban 90 s a un micrófono que ya no vuelve y la
        conversación, terminada y al 100%, se daba por fallida.

        La señal de "queda otro paso" depende del modo: hablando es que vuelva
        el micrófono; eligiendo, que vuelva a haber respuestas que pulsar.
        """
        senal = "SpeechButton" if modo == "hablar" else "ChoiceButton"
        try:
            await self.page.get_by_test_id(senal).first.wait_for(
                state="visible", timeout=self.probe_timeout_ms
            )
            return True
        except PlaywrightTimeoutError:
            self.logger.info(
                "  La conversación se acabó en el paso %d (la API decía más)",
                step_number,
            )
            return False

    async def _input_mode(self) -> str:
        """Cómo se contesta esta actividad: ``hablar``, ``elegir`` o nada.

        Las dos conversaciones del árbol comparten reproductor y se distinguen
        por el ``inputType`` de sus pasos: ``speaking`` pinta el micrófono,
        ``select`` solo las respuestas. Antes se exigía el micrófono y se
        abandonaba sin él, que es lo que hacía imposible ``WithoutReco``: la
        actividad estaba bien, la que no servía era la espera.
        """
        try:
            await self.page.wait_for_function(
                "() => Boolean(document.querySelector('[data-qa=SpeechButton]') "
                "|| document.querySelector('[data-qa=ChoiceButton]'))",
                timeout=self.probe_timeout_ms,
            )
        except PlaywrightTimeoutError:
            return "desconocido"
        if await self.page.get_by_test_id("SpeechButton").count():
            return "hablar"
        return "elegir"

    async def _complete_visible_choice_step(self, step_number: int) -> bool:
        """Resuelve un paso que se contesta pulsando, sin micrófono de por medio.

        Aquí marcar la respuesta **sí es obligatorio**: hablando el reconocedor
        decide por ti aunque no marques nada, pero eligiendo no hay otra forma de
        contestar, así que un clic que no se registra es el final del paso.
        """
        prompt = self.page.get_by_test_id("PromptText").first
        previous_prompt = (await prompt.text_content() or "").strip()
        choices = self.page.get_by_test_id("ChoiceButton")
        if await choices.count() == 0:
            self.logger.error("  El paso %d no tiene respuestas", step_number)
            return False

        # El enunciado suena al entrar en el paso y el reproductor ignora los
        # clics mientras tanto: es la misma espera que hace la ruta hablada.
        await self._wait_for_silence()

        if not await self._select_choice(choices.first):
            self.logger.error(
                "  El paso %d no llegó a marcar ninguna respuesta", step_number
            )
            await self._dump_screenshot("respuesta_no_marcada")
            return False

        if not await self._advance_to_next_step(previous_prompt):
            self.logger.error(
                "  El paso %d quedó marcado pero el reproductor no avanzó",
                step_number,
            )
            await self._dump_screenshot("sin_avanzar_de_paso")
            return False
        self.logger.info("  Paso %d resuelto eligiendo respuesta", step_number)
        return True

    async def _wait_until_recording(self) -> None:
        """Espera a que el botón entre en modo grabación antes de hablar.

        Inyectar el audio nada más pulsar se comía el principio de la frase: el
        primer intento salía casi siempre "Volver a intentar" y entraba el
        segundo. Parado quiere decir que el botón enseña el micrófono
        (``data-qa=MicIcon``); grabando, lo cambia por su animación. Es de mejor
        esfuerzo: si la señal no llega, se habla igual.
        """
        try:
            await self.page.wait_for_function(
                "() => { const b = document.querySelector('[data-qa=SpeechButton]'); "
                "return b && !b.querySelector('[data-qa=MicIcon]'); }",
                timeout=self.probe_timeout_ms,
            )
        except PlaywrightTimeoutError:
            self.logger.debug("  El micrófono no avisó de estar grabando; se sigue")

    async def _submit_verdict(self) -> str:
        """Qué dice el botón de enviar después de hablar.

        ``sin respuesta`` (sigue en "Omitir"), ``rechazada`` ("Volver a
        intentar") o ``aceptada`` (cualquier otra cosa, que es lo que deja
        pasar al enunciado siguiente).
        """
        leer = (
            "() => { const e = document.querySelector('[data-qa=SubmitButton]'); "
            "return e ? (e.getAttribute('data-qa-button-text') "
            "|| e.textContent || '').trim() : ''; }"
        )
        try:
            await self.page.wait_for_function(
                "() => { const e = document.querySelector('[data-qa=SubmitButton]'); "
                "if (!e) return false; "
                "const t = (e.getAttribute('data-qa-button-text') "
                "|| e.textContent || '').trim(); "
                "return Boolean(t) && !/^(skip|omitir)$/i.test(t); }",
                timeout=self.probe_timeout_ms,
            )
        except PlaywrightTimeoutError:
            return "sin respuesta"

        texto = await self.page.evaluate(leer)
        if re.match(r"^\s*(volver a intentar|try again|retry)\s*$", texto, re.I):
            return "rechazada"
        return "aceptada"

    async def _press_retry(self) -> bool:
        """Pulsa *Volver a intentar* para poder hablar otra vez."""
        try:
            await self.page.get_by_test_id("SubmitButton").first.click(
                force=True, timeout=self.probe_timeout_ms
            )
        except Exception as error:  # noqa: BLE001 - sin reintento, se abandona
            self.logger.info("  No se pudo volver a intentar: %s", error)
            return False
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
            # ``arg`` es keyword-only en Playwright: pasarlo por posición es un
            # TypeError, y aquí salía disfrazado de "Speech browser flow failed"
            # en mitad de la actividad, no al arrancar.
            if arg is None:
                await self.page.wait_for_function(expression, timeout=self.timeout_ms)
            else:
                await self.page.wait_for_function(
                    expression, arg=arg, timeout=self.timeout_ms
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
        # El clic por DOM va primero porque es el que acierta: en las trazas
        # resuelve en 0,5-2,5 s, mientras que el clic con ``force`` agota sus
        # 8 s casi siempre y solo después se probaba este. Ir en el otro orden
        # costaba ~8 s por paso comprando un fallo conocido.
        intentos = (
            ("el altavoz por DOM", lambda: listen.first.evaluate("el => el.click()")),
            ("el altavoz", lambda: listen.first.click(force=True, timeout=self.probe_timeout_ms)),
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

    async def _dismiss_microphone_check(self) -> bool:
        """Cierra el modal de "Comprobación de micrófono".

        Es lo que bloqueaba la actividad entera: una capa por encima de todo
        con un desplegable de dispositivos y un botón *Comenzar*. Detrás de ella
        ningún clic llegaba a las respuestas y el micrófono seguía deshabilitado
        — durante once corridas pareció un problema de selectores.

        En un contenedor el desplegable sale vacío, así que además se elige el
        primer dispositivo que haya (el falso que inyecta el navegador o el que
        añade el guion del micrófono virtual).

        Tiene dos caras y solo la primera tiene botón: elegir dispositivo y
        pulsar *Comenzar*, y luego "Comprobando el micrófono...", que escucha
        sin nada que pulsar. Buscar el botón en la segunda daba "no se encontró
        el modal" mientras seguía tapando la pantalla, así que lo que se mira
        es la ventana (``CalibrationWindow``) y lo que se espera es que se vaya.
        """
        etiqueta = re.compile(r"^\s*(comenzar|start|continuar|continue)\s*$", re.I)
        try:
            estado = await self.page.evaluate(
                "() => window.__rosettaMicCheckState "
                "? window.__rosettaMicCheckState() : null"
            )
            if estado is not None and not estado.get("presente"):
                self.logger.debug("  Sin comprobación de micrófono en pantalla")
                return False
            # Con el guion sin instalar no se sabe si hay ventana, y decir
            # que sí haría que se volviera a pulsar el micrófono — que es
            # apagarlo. Ante la duda, no.
            hubo_ventana = estado is not None
            if estado is not None:
                self.logger.info(
                    "  Comprobación de micrófono en pantalla (%s): %s",
                    "escuchando" if estado.get("escuchando") else "eligiendo micrófono",
                    estado.get("texto"),
                )
                await self.page.evaluate(
                    "() => Boolean(window.__rosettaDismissMicCheck "
                    "&& window.__rosettaDismissMicCheck())"
                )
                if await self._wait_for_mic_check_to_pass():
                    return True

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
                return hubo_ventana

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
                return hubo_ventana
            # A nivel debug esto era invisible y el modal se quedaba abierto sin
            # que nada lo dijera: dos corridas perdidas por no ver esta línea.
            self.logger.info(
                "  No se encontró el botón del modal de micrófono (%s)",
                ", ".join(encontrados),
            )
            return hubo_ventana
        except Exception as error:  # noqa: BLE001 - puede no estar
            self.logger.debug("  No se pudo cerrar el modal de micrófono: %s", error)
        return False

    async def _wait_for_microphone(self, peticiones_antes: int) -> None:
        """Espera a que el reproductor tenga micrófono para este paso.

        Antes se ponía ``__rosettaMicReady`` a ``false`` y se esperaba a que
        ``getUserMedia`` lo devolviera a ``true``. Pero el reproductor pide el
        micrófono **una sola vez** —en la comprobación— y reutiliza ese
        ``MediaStream`` el resto de la actividad: la segunda petición no llega
        nunca y la espera moría a los 90 s con "que el reproductor pida el
        micrófono". Lo que hace falta es que el micrófono virtual esté
        conectado, no que lo vuelvan a pedir.
        """
        # Si ya hay micrófono conectado, esperar los 15 s del sondeo a una
        # petición que no va a llegar es peor que inútil: el reconocedor
        # escucha unos segundos y, si para entonces no ha oído nada, da la
        # respuesta por no entendida. El audio tiene que entrar enseguida.
        ya_listo = await self.page.evaluate("() => window.__rosettaMicReady === true")
        espera = 1_500 if ya_listo else self.probe_timeout_ms
        try:
            await self.page.wait_for_function(
                "antes => (window.__rosettaMicRequests || 0) > antes",
                arg=peticiones_antes,
                timeout=espera,
            )
            return
        except PlaywrightTimeoutError:
            pass

        if not ya_listo:
            raise RuntimeError(
                "el reproductor no pidió el micrófono y no hay ninguno conectado"
            )
        self.logger.debug("  El reproductor reutiliza el micrófono de la comprobación")

    async def _wait_for_mic_check_to_pass(self) -> bool:
        """Espera a que la ventana de calibración se vaya.

        Mientras está, va en ``position: fixed`` con ``z-index: 7000`` y tapa
        la actividad entera: seguir adelante solo servía para gastar los cinco
        intentos de pulsar una respuesta contra el modal y dar por fallado el
        paso. Si no se va, se dice con qué señal se quedó — el medidor
        (``encendidas``/``barras``) es lo que distingue "no llega audio" de
        "llega y no la reconoce".
        """
        try:
            await self.page.wait_for_function(
                "() => !document.querySelector('[data-qa=\"CalibrationWindow\"]')",
                timeout=self.timeout_ms,
            )
        except PlaywrightTimeoutError:
            estado = await self.page.evaluate(
                "() => window.__rosettaMicCheckState()"
            )
            self.logger.error(
                "  La comprobación de micrófono no pasó: medidor %s/%s, "
                "señal inyectada=%s",
                estado.get("encendidas"),
                estado.get("barras"),
                estado.get("senal"),
            )
            await self._dump_screenshot("comprobacion_microfono")
            return False
        self.logger.info("  Comprobación de micrófono superada")
        return True

    async def _wait_for_recognizer(self) -> None:
        """Espera a que el reconocedor termine de cargar su modelo.

        Lo anuncia por consola y el guion de captura lo apunta. Es de mejor
        esfuerzo: si la señal no llega, se sigue igual — pero pulsar antes de
        tiempo es lo que hacía que el altavoz no sonara en unas corridas sí y
        en otras no.
        """
        # La señal llega una vez o no llega nunca: en las cuatro trazas hay
        # exactamente un timeout por actividad, sean 3 o 9 las llamadas. Pagar
        # los 15 s en cada paso es pagar el mismo silencio muchas veces.
        if self._reconocedor_mudo:
            return
        try:
            await self.page.wait_for_function(
                "() => window.__rosettaSreReady === true",
                timeout=self.probe_timeout_ms,
            )
        except PlaywrightTimeoutError:
            self._reconocedor_mudo = True
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
                # Los aciertos tardan 0,5-2,5 s; 4 s es holgado. Si se queda
                # corto se ve en el log ("El altavoz de la respuesta no sonó")
                # y el audio de reserva ya está puesto.
                timeout=4_000,
            )
            return True
        except PlaywrightTimeoutError:
            return False

    async def _select_choice(self, choice: Any, *, exhaustivo: bool = True) -> bool:
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
        # Hablando no hace falta insistir: está medido que **ninguna** de las
        # cinco vías registra la marca (30/30, 15/15, 5/5 y 5/5 timeouts en
        # cuatro trazas), y no por mala suerte — la señal que se espera es que
        # el botón deje de decir "Omitir", y hablando eso no ocurre hasta que
        # hablas. Eran 10 s por paso comprando un no. Se conserva un intento,
        # con sonda corta, por si alguna vez ayuda.
        sonda_ms = 2_000 if exhaustivo else 500
        if not exhaustivo:
            intentos = intentos[:1]

        pintado_antes = await self._choice_paint(choice)
        for descripcion, intento in intentos:
            try:
                await intento(choice)
            except Exception as error:  # noqa: BLE001 - se prueba el siguiente
                self.logger.debug("  No se pudo pulsar %s: %s", descripcion, error)
                continue
            if await self._choice_registered(choice, pintado_antes, sonda_ms):
                self.logger.info("  Respuesta marcada pulsando %s", descripcion)
                return True
        return False

    async def _choice_paint(self, choice: Any) -> str:
        """Cómo está pintado el radio de esta respuesta.

        No hay ``aria-checked`` ni ``input[type=radio]``: la ficha es un ``div``
        con un SVG de dos círculos, y lo único que cambia al elegir es el
        relleno del interior (sin marcar: ``#ffffff``).
        """
        try:
            return await choice.evaluate(
                "el => [...el.querySelectorAll('circle')]"
                ".map(c => (c.getAttribute('fill') || '')).join('|')"
            )
        except Exception:  # noqa: BLE001 - es una comprobación, no puede hundir nada
            return ""

    async def _choice_registered(
        self, choice: Any, pintado_antes: str, sonda_ms: int = 2_000
    ) -> bool:
        """¿Se ha enterado el reproductor de que hemos elegido?

        Ya **no** vale que el micrófono esté habilitado: desde que la
        comprobación de micrófono se pasa, lo está siempre, así que ese criterio
        daba por buena la primera forma de pulsar y no se probaba ninguna otra —
        con la actividad entera sin una sola respuesta marcada.

        Lo que sirve es que el botón de enviar deje de decir "Omitir", o que el
        radio de *esta* respuesta cambie de aspecto.
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
                    return Boolean(yaNoOmite || marcado);
                }""",
                timeout=sonda_ms,
            )
            return True
        except PlaywrightTimeoutError:
            return await self._choice_paint(choice) != pintado_antes

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
        button = self.page.get_by_test_id("SpeechButton").first
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

        # Pueden sonar **dos** altavoces a la vez (el del enunciado y el de la
        # respuesta que acabamos de pulsar). Un locator con dos coincidencias
        # hace saltar el modo estricto de Playwright, y como esto ocurre a mitad
        # de la conversación se llevaba por delante la actividad entera con un
        # "Speech browser flow failed" que no dice nada del audio. ``count()`` no
        # avisa del choque: da 2, el ``if`` pasa, y revienta el ``wait_for``.
        #
        # Se espera por la condición en JS, que los cuenta a todos y no se casa
        # con ninguno — y que además es lo correcto: queremos silencio, no que se
        # vaya el primero de los dos.
        await self._wait_for_all_audio_to_stop()
        return body

    async def _wait_for_all_audio_to_stop(self) -> None:
        """Espera a que no quede ningún altavoz sonando. No falla si queda."""
        try:
            await self.page.wait_for_function(
                "() => !document.querySelector('[data-qa=audio_playing]')",
                timeout=self.timeout_ms,
            )
        except PlaywrightTimeoutError:
            self.logger.debug("  El reproductor sigue sonando; se continúa")
