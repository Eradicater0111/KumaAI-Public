from __future__ import annotations

import json
import os
import re
import tempfile
import uuid
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    QProcess,
    Signal,
)

from app.voice.voice_runtime import (
    VoiceOutputMode,
    VoiceSnapshot,
    idle_voice_snapshot,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)


class KumaSpeechController(QObject):
    """
    KUMA speech-output boundary.

    Primary:
        Persistent Kokoro MLX neural service.
        af_nova remains loaded in memory.

    Fallback:
        macOS Samantha.

    No agent, planner, model runtime, memory or tool authority
    exists inside this presentation layer.
    """

    # =====================================================
    # KUMA-VOICE-1B — TRUTHFUL TTS OUTPUT STATE
    # =====================================================
    #
    # SPEAK REQUEST != PLAYBACK START
    # QPROCESS STARTED == PLAYBACK TRUTH
    # VOICE OUTPUT STATE != COGNITIVE STATE
    # VOICE OUTPUT ERROR != TASK FAILURE
    # VOICE OUTPUT AUTHORITY = NONE
    #
    # VoiceSnapshot is a one-way observable I/O projection.
    # This adapter never grants permission, execution authority,
    # model control, task completion, or microphone state.
    # =====================================================

    speech_started = Signal()
    speech_finished = Signal()
    speech_error = Signal(str)

    voice_state_changed = Signal(object)
    voice_ready = Signal()
    PROFILE_NAME = "KUMA Nova Companion"

    DEFAULT_NEURAL_VOICE = "af_nova"
    DEFAULT_NEURAL_SPEED = 0.96

    DEFAULT_SYSTEM_VOICE = "Samantha"
    DEFAULT_SYSTEM_RATE = 166

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self._enabled = (
            os.getenv(
                "KUMA_TTS_ENABLED",
                "1",
            )
            .strip()
            .lower()
            not in {
                "0",
                "false",
                "no",
                "off",
            }
        )

        self._backend = (
            os.getenv(
                "KUMA_TTS_BACKEND",
                "neural",
            )
            .strip()
            .lower()
        )

        self._neural_voice = (
            os.getenv(
                "KUMA_NEURAL_VOICE",
                self.DEFAULT_NEURAL_VOICE,
            ).strip()
            or self.DEFAULT_NEURAL_VOICE
        )

        try:
            self._neural_speed = float(
                os.getenv(
                    "KUMA_NEURAL_SPEED",
                    str(
                        self.DEFAULT_NEURAL_SPEED
                    ),
                )
            )
        except ValueError:
            self._neural_speed = (
                self.DEFAULT_NEURAL_SPEED
            )

        self._neural_speed = max(
            0.70,
            min(
                self._neural_speed,
                1.30,
            ),
        )

        self._system_voice = (
            os.getenv(
                "KUMA_TTS_VOICE",
                self.DEFAULT_SYSTEM_VOICE,
            ).strip()
            or self.DEFAULT_SYSTEM_VOICE
        )

        try:
            self._system_rate = int(
                os.getenv(
                    "KUMA_TTS_RATE",
                    str(
                        self.DEFAULT_SYSTEM_RATE
                    ),
                )
            )
        except ValueError:
            self._system_rate = (
                self.DEFAULT_SYSTEM_RATE
            )

        self._system_rate = max(
            100,
            min(
                self._system_rate,
                260,
            ),
        )

        self._debug = (
            os.getenv(
                "KUMA_TTS_DEBUG",
                "0",
            )
            .strip()
            .lower()
            in {
                "1",
                "true",
                "yes",
                "on",
            }
        )

        self._voice_python = (
            ROOT
            / ".voice-venv"
            / "bin"
            / "python"
        )

        self._neural_worker = (
            ROOT
            / "app"
            / "voice"
            / "neural_tts_worker.py"
        )

        self._service = None
        self._service_ready = False
        self._service_buffer = b""

        self._player = None
        self._system_process = None

        self._generation = 0

        self._pending_text = None
        self._pending_generation = None

        self._active_text = None
        self._active_audio_file = None
        self._current_request_id = None

        self._request_generations = {}
        self._request_texts = {}

        self._shutting_down = False

        # Voice-1B begins from the frozen Voice-1A neutral
        # contract. Input remains UNAVAILABLE until a later
        # microphone phase supplies real capture truth.
        self._voice_snapshot = (
            idle_voice_snapshot()
        )

        print(
            "KUMA VOICE → "
            f"profile={self.PROFILE_NAME!r} "
            f"backend={self._backend!r} "
            f"voice={self.voice!r}"
        )

        if (
            self._enabled
            and self._backend == "neural"
        ):
            self._start_neural_service()

    # =====================================================
    # PUBLIC STATE
    # =====================================================

    @property
    def enabled(
        self,
    ) -> bool:
        return self._enabled

    @property
    def voice(
        self,
    ) -> str:
        if self._backend == "neural":
            return self._neural_voice

        return self._system_voice

    @property
    def backend(
        self,
    ) -> str:
        return self._backend

    @property
    def neural_ready(
        self,
    ) -> bool:
        return self._service_ready

    def set_enabled(
        self,
        enabled,
    ):
        self._enabled = bool(
            enabled
        )

        if not self._enabled:
            self.stop()
            return

        if (
            self._backend == "neural"
            and not self._service_running()
        ):
            self._start_neural_service()

    # =====================================================
    # SPEAK
    # =====================================================

    @property
    def voice_snapshot(
        self,
    ) -> VoiceSnapshot:
        """Return the latest immutable zero-authority voice state."""

        return self._voice_snapshot

    def _publish_output_state(
        self,
        mode,
        *,
        reason,
    ) -> VoiceSnapshot:
        """
        Publish one truthful speech-output transition.

        Voice-1B owns only the output half of VoiceSnapshot.
        Existing input mode, microphone truth, and transcript are
        preserved unchanged for future microphone/STT phases.

        playback_active is derived only from PLAYING and is never
        caller-supplied.
        """

        if not isinstance(
            mode,
            VoiceOutputMode,
        ):
            raise TypeError(
                "mode must be VoiceOutputMode."
            )

        current = (
            self._voice_snapshot
        )

        snapshot = VoiceSnapshot(
            input_mode=current.input_mode,
            output_mode=mode,
            microphone_active=(
                current.microphone_active
            ),
            playback_active=(
                mode
                == VoiceOutputMode.PLAYING
            ),
            transcript=current.transcript,
            reason=reason,
        )

        if snapshot == current:
            return current

        self._voice_snapshot = snapshot

        self.voice_state_changed.emit(
            snapshot
        )

        return snapshot

    def speak(
        self,
        text,
    ) -> bool:
        if not self._enabled:
            return False

        prepared = self._prepare_text(
            text
        )

        if not prepared:
            return False

        # Cancel playback/pending presentation, but keep the
        # expensive neural model alive.
        self.stop()

        generation = self._generation

        self._active_text = prepared

        self._publish_output_state(
            VoiceOutputMode.SYNTHESIZING,
            reason="speech output accepted",
        )

        if self._backend != "neural":
            return self._start_system(
                prepared,
                generation,
            )

        if not self._neural_available():
            print(
                "KUMA VOICE → neural environment unavailable; "
                "using Samantha."
            )

            return self._start_system(
                prepared,
                generation,
            )

        if not self._service_running():
            self._start_neural_service()

        if self._service_ready:
            self._submit_neural_request(
                prepared,
                generation,
            )
        else:
            # The first utterance waits for the one-time model load.
            # Once ready, it is submitted automatically.
            self._pending_text = prepared
            self._pending_generation = generation

            print(
                "KUMA VOICE → waiting for neural service warm-up..."
            )

        return True

    # =====================================================
    # PERSISTENT NEURAL SERVICE
    # =====================================================

    def _neural_available(
        self,
    ) -> bool:
        return (
            self._voice_python.is_file()
            and self._neural_worker.is_file()
        )

    def _service_running(
        self,
    ) -> bool:
        return (
            self._service is not None
            and self._service.state()
            != QProcess.ProcessState.NotRunning
        )

    def _start_neural_service(
        self,
    ):
        if (
            not self._neural_available()
            or self._service_running()
        ):
            return

        self._service_ready = False
        self._service_buffer = b""

        process = QProcess(
            self
        )

        self._service = process

        process.readyReadStandardOutput.connect(
            self._read_service_stdout
        )

        process.readyReadStandardError.connect(
            self._drain_service_stderr
        )

        process.finished.connect(
            self._on_service_finished
        )

        process.errorOccurred.connect(
            self._on_service_process_error
        )

        print(
            "KUMA VOICE → warming af_nova neural service..."
        )

        process.start(
            str(
                self._voice_python
            ),
            [
                str(
                    self._neural_worker
                )
            ],
        )

    def _read_service_stdout(
        self,
    ):
        process = self._service

        if process is None:
            return

        self._service_buffer += bytes(
            process.readAllStandardOutput()
        )

        while b"\n" in self._service_buffer:
            raw_line, self._service_buffer = (
                self._service_buffer.split(
                    b"\n",
                    1,
                )
            )

            line = (
                raw_line.decode(
                    "utf-8",
                    errors="replace",
                )
                .strip()
            )

            if not line:
                continue

            try:
                payload = json.loads(
                    line
                )
            except json.JSONDecodeError:
                if self._debug:
                    print(
                        "KUMA VOICE SERVICE → "
                        f"{line}"
                    )
                continue

            self._handle_service_event(
                payload
            )

    def _handle_service_event(
        self,
        payload,
    ):
        event = str(
            payload.get(
                "event",
                "",
            )
        )

        if event == "loading":
            print(
                "KUMA VOICE → neural model loading..."
            )
            return

        if event == "prewarming":
            print(
                "KUMA VOICE → "
                "prewarming Nova first inference..."
            )
            return

        if event == "prewarmed":
            print(
                "KUMA VOICE → "
                "Nova inference path warm."
            )
            return

        if event == "ready":
            self._service_ready = True
            print(
                "KUMA VOICE → "
                "af_nova neural service READY."
            )
            self.voice_ready.emit()
            self._submit_pending_if_current()
            return

        if event == "generating":
            request_id = str(
                payload.get(
                    "id",
                    "",
                )
            )

            generation = (
                self._request_generations.get(
                    request_id
                )
            )

            if generation == self._generation:
                print(
                    "KUMA VOICE → generating speech..."
                )

            return

        if event == "generated":
            self._handle_generated_event(
                payload
            )
            return

        if event == "error":
            self._handle_neural_error_event(
                payload
            )
            return

    def _submit_pending_if_current(
        self,
    ):
        text = self._pending_text
        generation = self._pending_generation

        self._pending_text = None
        self._pending_generation = None

        if (
            not text
            or generation != self._generation
        ):
            return

        self._submit_neural_request(
            text,
            generation,
        )

    def _submit_neural_request(
        self,
        text,
        generation,
    ):
        process = self._service

        if (
            process is None
            or not self._service_ready
        ):
            self._pending_text = text
            self._pending_generation = generation
            return

        request_id = uuid.uuid4().hex

        output = (
            Path(
                tempfile.gettempdir()
            )
            / f"kuma_tts_{request_id}.wav"
        )

        self._current_request_id = (
            request_id
        )

        self._active_audio_file = (
            output
        )

        self._request_generations[
            request_id
        ] = generation

        self._request_texts[
            request_id
        ] = text

        request = {
            "command": "speak",
            "id": request_id,
            "text": text,
            "output": str(
                output
            ),
            "voice": self._neural_voice,
            "speed": self._neural_speed,
        }

        process.write(
            (
                json.dumps(
                    request,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode(
                "utf-8"
            )
        )


    def _handle_generated_event(
        self,
        payload,
    ):
        request_id = str(
            payload.get(
                "id",
                "",
            )
        )

        generation = (
            self._request_generations.pop(
                request_id,
                None,
            )
        )

        self._request_texts.pop(
            request_id,
            None,
        )

        output_text = str(
            payload.get(
                "output",
                "",
            )
        )

        output = (
            Path(output_text)
            if output_text
            else None
        )

        if generation != self._generation:
            self._unlink(
                output
            )
            return

        if (
            request_id
            != self._current_request_id
        ):
            self._unlink(
                output
            )
            return

        if (
            output is None
            or not output.is_file()
            or output.stat().st_size <= 0
        ):
            self._fallback_current_text(
                "Neural service returned no audio."
            )
            return

        self._active_audio_file = (
            output
        )

        generation_seconds = payload.get(
            "generation_seconds"
        )

        if isinstance(
            generation_seconds,
            (int, float),
        ):
            print(
                "KUMA VOICE → neural speech ready "
                f"in {generation_seconds:.3f}s."
            )
        else:
            print(
                "KUMA VOICE → neural speech ready."
            )

        self._start_neural_playback(
            generation,
            output,
        )

    def _handle_neural_error_event(
        self,
        payload,
    ):
        request_id = str(
            payload.get(
                "id",
                "",
            )
        )

        message = str(
            payload.get(
                "error",
                "Unknown neural TTS error.",
            )
        )

        generation = (
            self._request_generations.pop(
                request_id,
                None,
            )
        )

        text = (
            self._request_texts.pop(
                request_id,
                None,
            )
        )

        if generation != self._generation:
            return

        print(
            "KUMA VOICE → neural generation failed: "
            f"{message}"
        )

        if text:
            self._start_system(
                text,
                generation,
            )

    def _drain_service_stderr(
        self,
    ):
        process = self._service

        if process is None:
            return

        data = bytes(
            process.readAllStandardError()
        )

        if (
            self._debug
            and data
        ):
            text = data.decode(
                "utf-8",
                errors="replace",
            ).strip()

            if text:
                print(
                    "KUMA VOICE SERVICE STDERR → "
                    f"{text}"
                )

    def _on_service_finished(
        self,
        exit_code,
        exit_status,
    ):
        del exit_status

        self._service_ready = False
        self._service = None

        if self._shutting_down:
            return

        print(
            "KUMA VOICE → neural service stopped "
            f"(code={exit_code})."
        )

        text = self._active_text

        if text:
            self._start_system(
                text,
                self._generation,
            )

    def _on_service_process_error(
        self,
        error,
    ):
        del error

        if self._shutting_down:
            return

        process = self._service

        if (
            process is not None
            and process.state()
            != QProcess.ProcessState.NotRunning
        ):
            return

        self._service_ready = False

        text = self._active_text

        if text:
            self._start_system(
                text,
                self._generation,
            )

    # =====================================================
    # PLAYBACK
    # =====================================================

    def _start_neural_playback(
        self,
        generation,
        audio_path,
    ):
        player = QProcess(
            self
        )

        self._player = (
            player
        )

        player.started.connect(
            lambda:
            self._emit_started_if_current(
                generation
            )
        )

        player.finished.connect(
            lambda exit_code, exit_status:
            self._on_playback_finished(
                generation,
                exit_code,
                exit_status,
            )
        )

        player.errorOccurred.connect(
            lambda error:
            self._on_playback_error(
                generation,
                error,
            )
        )

        player.start(
            "/usr/bin/afplay",
            [
                str(
                    audio_path
                )
            ],
        )

    def _on_playback_finished(
        self,
        generation,
        exit_code,
        exit_status,
    ):
        del exit_status

        if generation != self._generation:
            return

        self._player = None

        self._cleanup_active_audio()

        self._active_text = None
        self._current_request_id = None

        if exit_code == 0:
            self._publish_output_state(
                VoiceOutputMode.IDLE,
                reason="neural audio playback completed",
            )

            self.speech_finished.emit()
            return

        self._publish_output_state(
            VoiceOutputMode.ERROR,
            reason="neural audio playback failed",
        )

        self.speech_error.emit(
            "KUMA neural audio playback failed."
        )

    def _on_playback_error(
        self,
        generation,
        error,
    ):
        del error

        if generation != self._generation:
            return

        self._player = None

        self._cleanup_active_audio()

        self._publish_output_state(
            VoiceOutputMode.ERROR,
            reason="neural audio player failed",
        )

        self.speech_error.emit(
            "KUMA neural audio player failed."
        )

    # =====================================================
    # SAMANTHA FALLBACK
    # =====================================================

    def _fallback_current_text(
        self,
        reason,
    ):
        print(
            "KUMA VOICE → "
            f"{reason} Using Samantha fallback."
        )

        text = self._active_text

        if text:
            self._start_system(
                text,
                self._generation,
            )

    def _start_system(
        self,
        text,
        generation,
    ) -> bool:
        process = QProcess(
            self
        )

        self._system_process = (
            process
        )

        process.started.connect(
            lambda:
            self._emit_started_if_current(
                generation
            )
        )

        process.finished.connect(
            lambda exit_code, exit_status:
            self._on_system_finished(
                generation,
                exit_code,
                exit_status,
            )
        )

        process.errorOccurred.connect(
            lambda error:
            self._on_system_error(
                generation,
                error,
            )
        )

        process.start(
            "/usr/bin/say",
            [
                "-v",
                self._system_voice,
                "-r",
                str(
                    self._system_rate
                ),
                text,
            ],
        )

        return True

    def _on_system_finished(
        self,
        generation,
        exit_code,
        exit_status,
    ):
        del exit_status

        if generation != self._generation:
            return

        self._system_process = None
        self._active_text = None

        if exit_code == 0:
            self._publish_output_state(
                VoiceOutputMode.IDLE,
                reason="fallback speech playback completed",
            )

            self.speech_finished.emit()
            return

        self._publish_output_state(
            VoiceOutputMode.ERROR,
            reason="fallback speech failed",
        )

        self.speech_error.emit(
            "KUMA fallback speech failed."
        )

    def _on_system_error(
        self,
        generation,
        error,
    ):
        del error

        if generation != self._generation:
            return

        process = self._system_process

        message = (
            process.errorString()
            if process is not None
            else "Unknown fallback speech error."
        )

        self._system_process = None

        self._publish_output_state(
            VoiceOutputMode.ERROR,
            reason="fallback speech player failed",
        )

        self.speech_error.emit(
            message
        )

    # =====================================================
    # INTERRUPTION
    # =====================================================

    def stop(
        self,
    ):
        was_output_active = (
            self._voice_snapshot.output_mode
            != VoiceOutputMode.IDLE
        )

        # Invalidate callbacks belonging to previous speech.
        self._generation += 1

        self._pending_text = None
        self._pending_generation = None

        self._active_text = None
        self._current_request_id = None

        for process in (
            self._player,
            self._system_process,
        ):
            if (
                process is not None
                and process.state()
                != QProcess.ProcessState.NotRunning
            ):
                process.kill()

        self._player = None
        self._system_process = None

        self._cleanup_active_audio()

        if was_output_active:
            # Explicit interruption is the controller cancellation
            # boundary. Generation invalidation prevents the killed
            # process from later publishing stale terminal state.
            self._publish_output_state(
                VoiceOutputMode.IDLE,
                reason="speech output stopped",
            )

        # Deliberately keep the neural service alive.
        # Kokoro / af_nova remains resident and warm.


    def shutdown(
        self,
    ):
        self._shutting_down = True

        self.stop()

        process = self._service

        if (
            process is not None
            and process.state()
            != QProcess.ProcessState.NotRunning
        ):
            try:
                request = {
                    "command": "shutdown",
                }

                process.write(
                    (
                        json.dumps(
                            request
                        )
                        + "\n"
                    ).encode(
                        "utf-8"
                    )
                )

                process.waitForBytesWritten(
                    100
                )

            except Exception:
                pass

            if not process.waitForFinished(
                500
            ):
                process.terminate()

                if not process.waitForFinished(
                    500
                ):
                    process.kill()

        self._service = None
        self._service_ready = False

    # =====================================================
    # TEXT PREPARATION
    # =====================================================

    def _prepare_text(
        self,
        text,
    ) -> str:
        text = str(
            text
            or ""
        )

        # Visible branding stays KUMA.
        # Spoken form is Kuma.
        text = re.sub(
            r"\bKUMA\b",
            "Kuma",
            text,
        )

        # -------------------------------------------------
        # KUMA EMOJI SPEECH FILTER
        # -------------------------------------------------
        #
        # Emojis remain visible in the speech bubble and may
        # drive expression metadata, but neural TTS should not
        # literally describe them aloud.
        # -------------------------------------------------

        text = re.sub(
            (
                r"["
                r"\U0001F1E6-\U0001F1FF"
                r"\U0001F300-\U0001F5FF"
                r"\U0001F600-\U0001F64F"
                r"\U0001F680-\U0001F6FF"
                r"\U0001F700-\U0001F77F"
                r"\U0001F780-\U0001F7FF"
                r"\U0001F800-\U0001F8FF"
                r"\U0001F900-\U0001F9FF"
                r"\U0001FA00-\U0001FAFF"
                r"\u2600-\u27BF"
                r"\uFE0F"
                r"\u200D"
                r"\u20E3"
                r"]+"
            ),
            " ",
            text,
        )

        # -------------------------------------------------
# EMOJI / VISUAL EXPRESSION CLEANUP
# -------------------------------------------------
#
# Emojis remain visible in KUMA's speech bubble,
# but must never be literally described by TTS.
# Emotional meaning will later be routed into
# KUMA's expression/gesture system instead.
# -------------------------------------------------

        text = re.sub(
    (
        r"["
        r"\U0001F1E6-\U0001F1FF"
        r"\U0001F300-\U0001F5FF"
        r"\U0001F600-\U0001F64F"
        r"\U0001F680-\U0001F6FF"
        r"\U0001F700-\U0001F77F"
        r"\U0001F780-\U0001F7FF"
        r"\U0001F800-\U0001F8FF"
        r"\U0001F900-\U0001F9FF"
        r"\U0001FA00-\U0001FAFF"
        r"\u2600-\u27BF"
        r"\uFE0F"
        r"\u200D"
        r"]+"
    ),
    " ",
    text,
)

        # Don't read fenced code aloud.
        text = re.sub(
            r"```.*?```",
            " ",
            text,
            flags=re.DOTALL,
        )

        # Markdown links -> visible label.
        text = re.sub(
            r"\[([^\]]+)\]\([^)]+\)",
            r"\1",
            text,
        )

        text = text.replace(
            "`",
            "",
        )

        text = re.sub(
            r"(?m)^\s{0,3}#{1,6}\s*",
            "",
            text,
        )

        text = re.sub(
            r"(?m)^\s*[-*+]\s+",
            "",
            text,
        )

        text = re.sub(
            r"[*_~]",
            "",
            text,
        )

        text = re.sub(
            r"\s+",
            " ",
            text,
        ).strip()

        max_chars = 2200

        if len(text) > max_chars:
            text = text[:max_chars]

            if " " in text:
                text = text.rsplit(
                    " ",
                    1,
                )[0]

            text = (
                text.rstrip(
                    " ,;:-"
                )
                + "."
            )

        return text

    # =====================================================
    # HELPERS
    # =====================================================

    def _emit_started_if_current(
        self,
        generation,
    ):
        if generation == self._generation:
            self._publish_output_state(
                VoiceOutputMode.PLAYING,
                reason="audio playback started",
            )

            self.speech_started.emit()

    def _cleanup_active_audio(
        self,
    ):
        self._unlink(
            self._active_audio_file
        )

        self._active_audio_file = None

    @staticmethod
    def _unlink(
        path,
    ):
        if path is None:
            return

        try:
            Path(path).unlink(
                missing_ok=True
            )
        except OSError:
            pass
