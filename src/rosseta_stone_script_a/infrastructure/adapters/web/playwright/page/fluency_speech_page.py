"""Playwright workflow for Fluency conversation-practice activities.

The Gaia progress endpoint alone cannot complete ``DialogueExpressionWithReco``.
The lesson player needs a microphone MediaStream and its local speech recognizer
must produce the result. This adapter feeds the selected answer's own reference
audio into an in-page virtual microphone and lets the normal player submit it.
"""

from __future__ import annotations

import base64
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

  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (AudioContextClass && AudioContextClass.prototype.decodeAudioData) {
    const originalDecode = AudioContextClass.prototype.decodeAudioData;
    AudioContextClass.prototype.decodeAudioData = function(arrayBuffer, ...args) {
      if (
        window.__rosettaCaptureReference === true
        && arrayBuffer.byteLength > 1000
        && arrayBuffer.byteLength < 5000000
      ) {
        window.__rosettaReferenceAudio = encode(arrayBuffer.slice(0));
      }
      return originalDecode.call(this, arrayBuffer, ...args);
    };
  }

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
    def __init__(self, page: Page, timeout_ms: int = 90_000) -> None:
        self.page = page
        self.timeout_ms = timeout_ms

    async def complete_activity(
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
            await self.page.get_by_test_id("SpeechButton").wait_for(
                state="visible", timeout=self.timeout_ms
            )
            await self.page.evaluate(_VIRTUAL_MIC_SCRIPT)
            await self.page.evaluate(_REFERENCE_AUDIO_CAPTURE_SCRIPT)

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

        course = courses.filter(has_text=course_title)
        if await course.count() != 1:
            raise RuntimeError(f"course card not found uniquely: {course_title}")
        await course.get_by_test_id("LaunchCourseButton").click()

        lessons = self.page.get_by_test_id("LessonDisplayer")
        await lessons.first.wait_for(state="visible", timeout=self.timeout_ms)
        lesson = lessons.filter(has_text=lesson_title)
        if await lesson.count() != 1:
            raise RuntimeError(f"lesson card not found uniquely: {lesson_title}")
        await lesson.get_by_test_id("LaunchButton").click()
        await self.page.get_by_test_id("ActivityMapList").wait_for(
            state="visible", timeout=self.timeout_ms
        )

    async def _complete_visible_step(self, step_number: int) -> bool:
        prompt = self.page.get_by_test_id("PromptText")
        previous_prompt = (await prompt.text_content() or "").strip()
        choices = self.page.get_by_test_id("ChoiceButton")
        if await choices.count() == 0:
            self.logger.error("  Speech step %d has no choices", step_number)
            return False

        choice = choices.first
        audio = await self._capture_choice_audio(choice)
        await choice.click(force=True, timeout=self.timeout_ms)

        await self.page.evaluate(
            "() => { window.__rosettaMicReady = false; "
            "window.__rosettaMicPlaybackDone = false; }"
        )
        await self.page.get_by_test_id("SpeechButton").click()
        await self.page.wait_for_function(
            "() => window.__rosettaMicReady === true", timeout=self.timeout_ms
        )
        await self.page.evaluate(
            "audio => window.__rosettaFeedMicrophone(audio)",
            base64.b64encode(audio).decode("ascii"),
        )
        await self.page.wait_for_function(
            "() => window.__rosettaMicPlaybackDone === true",
            timeout=self.timeout_ms,
        )

        submit = self.page.get_by_test_id("SubmitButton")
        await self.page.wait_for_function(
            "() => { const e = document.querySelector('[data-qa=SubmitButton]'); "
            "return e && !/^(skip|omitir)$/i.test((e.textContent || '').trim()); }",
            timeout=self.timeout_ms,
        )
        await submit.click()
        await self.page.wait_for_function(
            "oldPrompt => { const e = document.querySelector('[data-qa=PromptText]'); "
            "return !e || (e.textContent || '').trim() !== oldPrompt; }",
            previous_prompt,
            timeout=self.timeout_ms,
        )
        return True

    async def _capture_choice_audio(self, choice: Any) -> bytes:
        listen = choice.get_by_test_id("ListenButton")
        if await listen.count() == 0:
            # Some player versions render the speaker as a sibling while keeping
            # the same order as ChoiceButton.
            listen = self.page.get_by_test_id("ListenButton").last

        await self.page.evaluate(
            "() => { window.__rosettaReferenceAudio = null; "
            "window.__rosettaReferenceAudioUrl = null; "
            "window.__rosettaCaptureReference = true; }"
        )
        try:
            # The player places a decorative layer over the speaker icon. The
            # target is a stable data-qa control, so dispatch the same click
            # directly instead of waiting for that layer to stop intercepting.
            await listen.click(force=True, timeout=self.timeout_ms)
            await self.page.wait_for_function(
                "() => Boolean(window.__rosettaReferenceAudio || "
                "window.__rosettaReferenceAudioUrl)",
                timeout=self.timeout_ms,
            )
            captured = await self.page.evaluate(
                "() => ({ audio: window.__rosettaReferenceAudio, "
                "url: window.__rosettaReferenceAudioUrl })"
            )
        finally:
            await self.page.evaluate(
                "() => { window.__rosettaCaptureReference = false; }"
            )

        encoded_audio = captured.get("audio")
        if encoded_audio:
            body = base64.b64decode(encoded_audio)
        else:
            audio_response = await self.page.request.get(captured["url"])
            if not audio_response.ok:
                raise RuntimeError(
                    f"reference speech audio returned {audio_response.status}"
                )
            body = await audio_response.body()

        if not body:
            raise RuntimeError("reference speech audio response was empty")

        playing = self.page.locator('[data-qa="audio_playing"]')
        if await playing.count():
            await playing.wait_for(state="detached", timeout=self.timeout_ms)
        return body
