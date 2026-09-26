"""
KUMA STT-1D — main-process owner for an isolated local recognizer service.

The owner never imports MLX, NumPy, or mlx_whisper. Those dependencies belong
only to the .voice-venv worker process.

No process is started by construction. start() is explicit and requires a
pre-existing local model directory. recognize() accepts only frozen STT-1C
normalized audio and emits only frozen VoiceTranscript observations.

START RECOGNIZER != MICROPHONE CONSENT
RECOGNIZER READY != USER TURN
VoiceTranscript != TOOL PERMISSION
RECOGNIZER OWNER != RUNTIME OWNER
AUTHORITY = NONE
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
import uuid

from PySide6.QtCore import (
    QObject,
    QProcess,
    Signal,
)

from app.voice.stt_utterance_normalization import (
    STTNormalizedUtterance,
)
from app.voice.voice_runtime import (
    VoiceTranscript,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

MAX_SERVICE_BUFFER_BYTES = (
    256_000
)


class KumaSTTRecognizerOwner(
    QObject
):
    """
    Explicit zero-authority owner of one isolated recognizer subprocess.
    """

    transcript_ready = Signal(
        object
    )

    recognizer_error = Signal(
        str
    )

    recognizer_ready_changed = Signal(
        bool
    )

    def __init__(
        self,
        *,
        model_path,
        voice_python=None,
        worker_path=None,
        process_factory=None,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self._model_path = Path(
            model_path
        ).expanduser()

        self._voice_python = (
            Path(
                voice_python
            )
            if voice_python is not None
            else (
                ROOT
                / ".voice-venv"
                / "bin"
                / "python"
            )
        )

        self._worker_path = (
            Path(
                worker_path
            )
            if worker_path is not None
            else (
                ROOT
                / "app"
                / "voice"
                / "stt_recognizer_worker.py"
            )
        )

        self._process_factory = (
            process_factory
            if process_factory is not None
            else QProcess
        )

        if not callable(
            self._process_factory
        ):
            raise TypeError(
                "process_factory must be callable."
            )

        self._service = None
        self._service_ready = False
        self._service_buffer = b""
        self._pending_request_id = None
        self._shutting_down = False

    @property
    def service_ready(
        self,
    ) -> bool:
        return (
            self._service_ready
        )

    @property
    def request_pending(
        self,
    ) -> bool:
        return (
            self._pending_request_id
            is not None
        )

    def _local_model_available(
        self,
    ) -> bool:
        path = (
            self._model_path
        )

        if (
            not path.is_absolute()
            or not path.is_dir()
        ):
            return False

        if not (
            path
            / "config.json"
        ).is_file():
            return False

        return any(
            (
                path
                / name
            ).is_file()
            for name in (
                "weights.safetensors",
                "weights.npz",
            )
        )

    def _service_running(
        self,
    ) -> bool:
        process = (
            self._service
        )

        if process is None:
            return False

        try:
            return (
                process.state()
                != QProcess.ProcessState.NotRunning
            )
        except Exception:
            return False

    def _set_ready(
        self,
        value,
    ) -> None:
        value = bool(
            value
        )

        if (
            value
            == self._service_ready
        ):
            return

        self._service_ready = (
            value
        )

        self.recognizer_ready_changed.emit(
            value
        )

    def start(
        self,
    ) -> bool:
        """
        Explicitly start the isolated service.

        This method never provisions a package or downloads a model.
        """

        if (
            self._shutting_down
            or self._service_running()
        ):
            return False

        if (
            not self._voice_python.is_file()
            or not self._worker_path.is_file()
            or not self._local_model_available()
        ):
            return False

        process = (
            self._process_factory(
                self
            )
        )

        self._service = (
            process
        )

        self._service_buffer = b""
        self._pending_request_id = (
            None
        )

        self._set_ready(
            False
        )

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

        process.start(
            str(
                self._voice_python
            ),
            [
                str(
                    self._worker_path
                ),
                "--model",
                str(
                    self._model_path
                ),
            ],
        )

        return True

    def recognize(
        self,
        utterance,
    ) -> str | None:
        """
        Send one normalized utterance to an already-ready worker.

        No raw audio is retained on this owner after process.write().
        """

        if not isinstance(
            utterance,
            STTNormalizedUtterance,
        ):
            raise TypeError(
                "utterance must be STTNormalizedUtterance."
            )

        if (
            not self._service_ready
            or not self._service_running()
            or self._pending_request_id
            is not None
        ):
            return None

        process = (
            self._service
        )

        if process is None:
            return None

        request_id = (
            uuid.uuid4().hex
        )

        encoded = base64.b64encode(
            utterance.pcm_s16le
        ).decode(
            "ascii"
        )

        request = {
            "command": "transcribe",
            "id": request_id,
            "audio_b64": encoded,
        }

        wire = (
            json.dumps(
                request,
                ensure_ascii=False,
                separators=(
                    ",",
                    ":",
                ),
            )
            + "\n"
        ).encode(
            "utf-8"
        )

        process.write(
            wire
        )

        self._pending_request_id = (
            request_id
        )

        return request_id

    def _read_service_stdout(
        self,
    ) -> None:
        process = (
            self._service
        )

        if process is None:
            return

        try:
            incoming = bytes(
                process.readAllStandardOutput()
            )
        except Exception:
            incoming = b""

        if not incoming:
            return

        self._service_buffer += (
            incoming
        )

        if (
            len(
                self._service_buffer
            )
            > MAX_SERVICE_BUFFER_BYTES
        ):
            self._service_buffer = b""
            self._pending_request_id = (
                None
            )

            self._set_ready(
                False
            )

            self.recognizer_error.emit(
                "KUMA speech recognition service protocol failed."
            )
            return

        while (
            b"\n"
            in self._service_buffer
        ):
            (
                raw_line,
                self._service_buffer,
            ) = (
                self._service_buffer
                .split(
                    b"\n",
                    1,
                )
            )

            self._handle_event_line(
                raw_line
            )

    def _handle_event_line(
        self,
        raw_line,
    ) -> None:
        try:
            payload = json.loads(
                raw_line.decode(
                    "utf-8"
                )
            )
        except Exception:
            self.recognizer_error.emit(
                "KUMA speech recognition service protocol failed."
            )
            return

        if not isinstance(
            payload,
            dict,
        ):
            self.recognizer_error.emit(
                "KUMA speech recognition service protocol failed."
            )
            return

        event = payload.get(
            "event"
        )

        if event == "ready":
            self._set_ready(
                True
            )
            return

        if event == "unavailable":
            self._pending_request_id = (
                None
            )

            self._set_ready(
                False
            )

            self.recognizer_error.emit(
                "KUMA speech recognition service is unavailable."
            )
            return

        if event == "error":
            request_id = payload.get(
                "id"
            )

            if (
                request_id
                and request_id
                != self._pending_request_id
            ):
                return

            self._pending_request_id = (
                None
            )

            self.recognizer_error.emit(
                "KUMA speech recognition failed."
            )
            return

        if event != "transcript":
            return

        request_id = payload.get(
            "id"
        )

        if (
            request_id
            != self._pending_request_id
        ):
            return

        text = payload.get(
            "text"
        )

        is_final = payload.get(
            "is_final"
        )

        self._pending_request_id = (
            None
        )

        try:
            transcript = (
                VoiceTranscript(
                    text=text,
                    is_final=is_final,
                )
            )
        except Exception:
            self.recognizer_error.emit(
                "KUMA speech recognition returned invalid text."
            )
            return

        self.transcript_ready.emit(
            transcript
        )

    def _drain_service_stderr(
        self,
    ) -> None:
        process = (
            self._service
        )

        if process is None:
            return

        try:
            process.readAllStandardError()
        except Exception:
            pass

    def _on_service_finished(
        self,
        *_args,
    ) -> None:
        self._service = None
        self._service_buffer = b""
        self._pending_request_id = (
            None
        )

        self._set_ready(
            False
        )

    def _on_service_process_error(
        self,
        _error,
    ) -> None:
        if self._shutting_down:
            return

        self._pending_request_id = (
            None
        )

        self._set_ready(
            False
        )

        self.recognizer_error.emit(
            "KUMA speech recognition service process failed."
        )

    def shutdown(
        self,
    ) -> None:
        self._shutting_down = True
        self._pending_request_id = (
            None
        )

        process = (
            self._service
        )

        if (
            process is not None
            and self._service_running()
        ):
            try:
                process.write(
                    b'{"command":"shutdown"}\n'
                )

                process.waitForBytesWritten(
                    100
                )
            except Exception:
                pass

            try:
                finished = (
                    process.waitForFinished(
                        500
                    )
                )
            except Exception:
                finished = False

            if not finished:
                try:
                    process.terminate()
                except Exception:
                    pass

                try:
                    finished = (
                        process.waitForFinished(
                            500
                        )
                    )
                except Exception:
                    finished = False

                if not finished:
                    try:
                        process.kill()
                    except Exception:
                        pass

        self._service = None
        self._service_buffer = b""

        self._set_ready(
            False
        )
