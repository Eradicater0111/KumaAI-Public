"""
KUMA-VOICE-1C — truthful microphone capture boundary.

This module owns only microphone capture truth.

Core boundaries:

- MICROPHONE REQUEST != MICROPHONE ACTIVE
- DEVICE AVAILABLE != CAPTURING
- QAudioSource EXISTS != CAPTURING
- QAudioSource.start() CALLED != CAPTURING
- FIRST NON-EMPTY AUDIO BYTES == CAPTURE EVIDENCE
- CAPTURING <=> microphone_active
- CAPTURE ERROR != TASK FAILURE
- MICROPHONE INPUT != COMMAND AUTHORITY
- MICROPHONE INPUT != PERMISSION
- MICROPHONE INPUT != EXECUTION
- MICROPHONE AUTHORITY = NONE

Voice-1C does not transcribe, persist, interpret, route, upload, or model-process
audio. Captured bytes are drained from Qt and immediately discarded by this
capture owner after an optional synchronous STT-1A handoff. The capture owner
never retains the raw payload and handoff failure never changes microphone truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable

from PySide6.QtCore import (
    QObject,
    Signal,
)

from PySide6.QtMultimedia import (
    QAudio,
    QAudioSource,
    QMediaDevices,
)

from app.voice.voice_runtime import (
    VOICE_AUTHORITY_NONE,
    VOICE_REASON_MAX_CHARS,
    VoiceInputMode,
)

from app.voice.stt_audio_handoff import (
    STTNativeAudioFormat,
    deliver_ephemeral_native_audio,
)


_ALLOWED_CAPTURE_MODES = frozenset(
    {
        VoiceInputMode.UNAVAILABLE,
        VoiceInputMode.INACTIVE,
        VoiceInputMode.CAPTURING,
        VoiceInputMode.ERROR,
    }
)


def _normalize_reason(
    value: str,
) -> str:
    if type(value) is not str:
        raise TypeError(
            "reason must be str."
        )

    normalized = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    if len(
        normalized
    ) > VOICE_REASON_MAX_CHARS:
        raise ValueError(
            "reason must be <= "
            f"{VOICE_REASON_MAX_CHARS} characters."
        )

    return normalized


@dataclass(
    frozen=True,
    slots=True,
)
class MicrophoneCaptureObservation:
    """
    Immutable zero-authority observation of microphone capture truth.

    This is deliberately input-only. It does not fabricate or overwrite
    output/playback state from KUMA-VOICE-1B. A later integration phase can
    project this observation into the unified VoiceSnapshot owned by the live
    voice runtime.
    """

    input_mode: VoiceInputMode = (
        VoiceInputMode.UNAVAILABLE
    )

    microphone_active: bool = False

    reason: str = ""

    authority: str = field(
        default=VOICE_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.input_mode,
            VoiceInputMode,
        ):
            raise TypeError(
                "input_mode must be VoiceInputMode."
            )

        if (
            self.input_mode
            not in _ALLOWED_CAPTURE_MODES
        ):
            raise ValueError(
                "microphone capture observations may use only "
                "UNAVAILABLE, INACTIVE, CAPTURING, or ERROR."
            )

        if type(
            self.microphone_active
        ) is not bool:
            raise TypeError(
                "microphone_active must be bool."
            )

        capturing = (
            self.input_mode
            == VoiceInputMode.CAPTURING
        )

        if (
            capturing
            != self.microphone_active
        ):
            raise ValueError(
                "microphone_active must be true exactly when "
                "input_mode is CAPTURING."
            )

        object.__setattr__(
            self,
            "reason",
            _normalize_reason(
                self.reason
            ),
        )


class KumaMicrophoneCapture(
    QObject
):
    """
    Local Qt microphone-capture boundary.

    start_capture() means only that a capture attempt was accepted. The
    controller does not publish CAPTURING until a non-empty byte sequence has
    actually been read from the QIODevice returned by QAudioSource.start().

    Raw audio is never retained by Voice-1C. Each readyRead event is drained
    and discarded after its byte length is observed.
    """

    capture_state_changed = Signal(
        object
    )

    capture_error = Signal(
        str
    )

    def __init__(
        self,
        parent=None,
        *,
        device_provider: Callable | None = None,
        source_factory: Callable | None = None,
        audio_consumer=None,
    ):
        super().__init__(
            parent
        )

        self._device_provider = (
            device_provider
            or QMediaDevices.defaultAudioInput
        )

        self._source_factory = (
            source_factory
            or self._default_source_factory
        )

        if (
            audio_consumer is not None
            and not callable(
                audio_consumer
            )
        ):
            raise TypeError(
                "audio_consumer must be callable or None."
            )

        self._audio_consumer = (
            audio_consumer
        )

        self._observation = (
            MicrophoneCaptureObservation()
        )

        self._source = None
        self._io_device = None

        self._generation = 0
        self._capture_requested = False

        self._device_available = False
        self._device_description = ""

        self._bytes_observed = 0

    @staticmethod
    def _default_source_factory(
        device,
        audio_format,
        parent,
    ):
        return QAudioSource(
            device,
            audio_format,
            parent,
        )

    @property
    def observation(
        self,
    ) -> MicrophoneCaptureObservation:
        return self._observation

    @property
    def capture_requested(
        self,
    ) -> bool:
        return self._capture_requested

    @property
    def bytes_observed(
        self,
    ) -> int:
        return self._bytes_observed

    @property
    def device_available(
        self,
    ) -> bool:
        return self._device_available

    @property
    def device_description(
        self,
    ) -> str:
        return self._device_description

    def _publish(
        self,
        mode,
        *,
        reason,
    ) -> MicrophoneCaptureObservation:
        observation = (
            MicrophoneCaptureObservation(
                input_mode=mode,
                microphone_active=(
                    mode
                    == VoiceInputMode.CAPTURING
                ),
                reason=reason,
            )
        )

        if (
            observation
            == self._observation
        ):
            return self._observation

        self._observation = (
            observation
        )

        self.capture_state_changed.emit(
            observation
        )

        return observation

    def _resolve_default_input(
        self,
    ):
        try:
            device = (
                self._device_provider()
            )
        except Exception:
            self._device_available = (
                False
            )
            self._device_description = ""
            return (
                None,
                None,
                "microphone device discovery failed",
            )

        if (
            device is None
            or device.isNull()
        ):
            self._device_available = False
            self._device_description = ""
            return (
                None,
                None,
                "no microphone input device available",
            )

        try:
            audio_format = (
                device.preferredFormat()
            )
        except Exception:
            self._device_available = False
            self._device_description = ""
            return (
                None,
                None,
                "microphone preferred format unavailable",
            )

        if (
            audio_format is None
            or not audio_format.isValid()
        ):
            self._device_available = False
            self._device_description = ""
            return (
                None,
                None,
                "microphone preferred format invalid",
            )

        try:
            description = (
                device.description()
            )
        except Exception:
            description = ""

        self._device_available = True
        self._device_description = str(
            description
            or ""
        )

        return (
            device,
            audio_format,
            "",
        )

    def probe_availability(
        self,
    ) -> bool:
        """
        Discover the default input device without starting capture.
        """

        if self._capture_requested:
            return (
                self._device_available
            )

        (
            device,
            audio_format,
            reason,
        ) = self._resolve_default_input()

        del audio_format

        if device is None:
            self._publish(
                VoiceInputMode.UNAVAILABLE,
                reason=reason,
            )
            return False

        self._publish(
            VoiceInputMode.INACTIVE,
            reason="microphone available; capture inactive",
        )
        return True

    def start_capture(
        self,
    ) -> bool:
        """
        Request local microphone capture.

        True means the Qt capture session was started and a QIODevice was
        obtained. It does NOT mean microphone_active is true. CAPTURING is
        published only after the first non-empty audio bytes are read.
        """

        if self._capture_requested:
            return False

        self._generation += 1
        generation = self._generation
        self._bytes_observed = 0

        (
            device,
            audio_format,
            reason,
        ) = self._resolve_default_input()

        if device is None:
            self._publish(
                VoiceInputMode.UNAVAILABLE,
                reason=reason,
            )
            return False

        self._publish(
            VoiceInputMode.INACTIVE,
            reason="microphone available; capture not yet proven",
        )

        try:
            source = (
                self._source_factory(
                    device,
                    audio_format,
                    self,
                )
            )
        except Exception:
            self._publish(
                VoiceInputMode.ERROR,
                reason="microphone audio source creation failed",
            )
            self.capture_error.emit(
                "KUMA microphone audio source creation failed."
            )
            return False

        if source is None:
            self._publish(
                VoiceInputMode.ERROR,
                reason="microphone audio source unavailable",
            )
            self.capture_error.emit(
                "KUMA microphone audio source unavailable."
            )
            return False

        self._source = source
        self._capture_requested = True

        source.stateChanged.connect(
            lambda state:
            self._on_source_state_changed(
                generation,
                state,
            )
        )

        try:
            io_device = (
                source.start()
            )
        except Exception:
            self._fail_current_session(
                generation,
                "microphone capture start failed",
                "KUMA microphone capture start failed.",
            )
            return False

        if io_device is None:
            self._fail_current_session(
                generation,
                "microphone capture returned no audio device",
                "KUMA microphone capture returned no audio device.",
            )
            return False

        if (
            generation
            != self._generation
            or not self._capture_requested
        ):
            try:
                io_device.close()
            except Exception:
                pass
            return False

        self._io_device = io_device

        io_device.readyRead.connect(
            lambda:
            self._on_ready_read(
                generation,
                audio_format,
            )
        )

        # If Qt made bytes available before readyRead was connected,
        # drain once immediately. Empty data still proves nothing.
        self._on_ready_read(
            generation,
            audio_format,
        )

        return True

    def _offer_audio_to_stt(
        self,
        payload,
        audio_format,
    ) -> None:
        """
        Offer one already-read native payload through frozen STT-1A.

        Metadata extraction and consumer failure are fail-soft and never
        redefine microphone capture truth. No raw payload or handoff
        observation is retained on this controller.
        """

        consumer = (
            self._audio_consumer
        )

        if (
            consumer is None
            or audio_format is None
        ):
            return

        try:
            sample_format = (
                audio_format.sampleFormat()
            )

            sample_format_name = (
                getattr(
                    sample_format,
                    "name",
                    None,
                )
                or str(
                    sample_format
                )
            )

            native_format = (
                STTNativeAudioFormat(
                    sample_rate_hz=int(
                        audio_format.sampleRate()
                    ),
                    channel_count=int(
                        audio_format.channelCount()
                    ),
                    sample_format=str(
                        sample_format_name
                    ),
                )
            )

            deliver_ephemeral_native_audio(
                payload,
                native_format,
                consumer,
            )
        except Exception:
            # STT metadata/consumer failure must not become microphone
            # capture failure. Frozen STT-1A has zero authority here.
            return

    def _on_ready_read(
        self,
        generation,
        audio_format=None,
    ) -> None:
        if (
            generation
            != self._generation
            or not self._capture_requested
        ):
            return

        io_device = self._io_device

        if io_device is None:
            return

        try:
            payload = bytes(
                io_device.readAll()
            )
        except Exception:
            self._fail_current_session(
                generation,
                "microphone audio read failed",
                "KUMA microphone audio read failed.",
            )
            return

        if not payload:
            return

        # Voice-1C deliberately retains only the count, never raw audio.
        self._bytes_observed += len(
            payload
        )

        if (
            self._observation.input_mode
            != VoiceInputMode.CAPTURING
        ):
            self._publish(
                VoiceInputMode.CAPTURING,
                reason="microphone audio bytes observed",
            )

        self._offer_audio_to_stt(
            payload,
            audio_format,
        )

    def _source_error(
        self,
    ):
        source = self._source

        if source is None:
            return None

        try:
            return source.error()
        except Exception:
            return None

    def _on_source_state_changed(
        self,
        generation,
        state,
    ) -> None:
        if (
            generation
            != self._generation
            or not self._capture_requested
        ):
            return

        if (
            state
            != QAudio.State.StoppedState
        ):
            return

        error = self._source_error()

        if (
            error is not None
            and error
            != QAudio.Error.NoError
        ):
            self._fail_current_session(
                generation,
                "microphone capture failed",
                "KUMA microphone capture failed.",
            )
            return

        self._fail_current_session(
            generation,
            "microphone capture stopped unexpectedly",
            "KUMA microphone capture stopped unexpectedly.",
        )

    def _fail_current_session(
        self,
        generation,
        reason,
        message,
    ) -> None:
        if (
            generation
            != self._generation
        ):
            return

        self._generation += 1
        self._capture_requested = False

        source = self._source
        io_device = self._io_device

        self._source = None
        self._io_device = None

        if source is not None:
            try:
                source.stop()
            except Exception:
                pass

        if io_device is not None:
            try:
                io_device.close()
            except Exception:
                pass

        self._publish(
            VoiceInputMode.ERROR,
            reason=reason,
        )

        self.capture_error.emit(
            message
        )

    def stop_capture(
        self,
    ) -> bool:
        """
        Stop the current local capture session.

        The generation is invalidated before QAudioSource.stop(), so any
        delayed state/readyRead signal from the old native source is stale and
        cannot overwrite the explicit terminal INACTIVE observation.
        """

        had_session = (
            self._capture_requested
            or self._source is not None
            or self._io_device is not None
            or self._observation.input_mode
            == VoiceInputMode.CAPTURING
        )

        if not had_session:
            return False

        self._generation += 1
        self._capture_requested = False

        source = self._source
        io_device = self._io_device

        self._source = None
        self._io_device = None

        if source is not None:
            try:
                source.stop()
            except Exception:
                pass

        if io_device is not None:
            try:
                io_device.close()
            except Exception:
                pass

        terminal_mode = (
            VoiceInputMode.INACTIVE
            if self._device_available
            else VoiceInputMode.UNAVAILABLE
        )

        self._publish(
            terminal_mode,
            reason=(
                "microphone capture stopped"
                if self._device_available
                else "microphone unavailable"
            ),
        )

        return True

    def close(
        self,
    ) -> None:
        self.stop_capture()
