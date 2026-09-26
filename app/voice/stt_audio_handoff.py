"""
KUMA STT-1A — zero-authority ephemeral native-audio handoff contract.

This module defines the narrow seam between truthful microphone capture and a
future speech-to-text process owner.

It deliberately does NOT:
- open or stop a microphone
- choose or normalize a QAudioFormat
- buffer an utterance
- retain raw audio
- transcribe audio
- create a VoiceTranscript
- submit a user turn
- call KumaGUIRuntime / KumaAgent
- start a model or process
- grant permission, confirmation, or execution authority

Voice-1C remains the microphone-capture truth owner. Its current
device.preferredFormat() semantics remain untouched.

A future capture adapter may synchronously offer each already-read non-empty
native payload through deliver_ephemeral_native_audio(). The dispatcher keeps
no payload state and returns only metadata/status. Consumer failure is
fail-soft with respect to microphone capture.

RAW AUDIO != USER COMMAND
AUDIO HANDOFF != TRANSCRIPT
PARTIAL TRANSCRIPT != USER TURN
FINAL TRANSCRIPT != TOOL PERMISSION
STT != RUNTIME OWNER
CONSUMER FAILURE != MICROPHONE FAILURE
AUTHORITY:NONE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, TypeAlias

from app.voice.voice_runtime import (
    VOICE_AUTHORITY_NONE,
)


STT_AUDIO_SAMPLE_FORMAT_MAX_CHARS = 64
STT_AUDIO_REASON_MAX_CHARS = 160


class STTAudioHandoffStatus(str, Enum):
    """
    Zero-authority result of one ephemeral raw-audio handoff attempt.
    """

    EMPTY = "empty"
    NO_CONSUMER = "no_consumer"
    DELIVERED = "delivered"
    CONSUMER_ERROR = "consumer_error"


@dataclass(
    frozen=True,
    slots=True,
)
class STTNativeAudioFormat:
    """
    Minimal immutable description of the native bytes read by Voice-1C.

    Values describe the QAudioFormat selected by the capture owner. They do not
    request a new format and they do not imply that audio has been normalized
    for any speech model.
    """

    sample_rate_hz: int
    channel_count: int
    sample_format: str

    authority: str = field(
        default=VOICE_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if (
            type(
                self.sample_rate_hz
            )
            is not int
            or self.sample_rate_hz <= 0
        ):
            raise ValueError(
                "sample_rate_hz must be a positive int."
            )

        if (
            type(
                self.channel_count
            )
            is not int
            or self.channel_count <= 0
        ):
            raise ValueError(
                "channel_count must be a positive int."
            )

        if not isinstance(
            self.sample_format,
            str,
        ):
            raise TypeError(
                "sample_format must be str."
            )

        normalized = (
            self.sample_format
            .strip()
        )

        if not normalized:
            raise ValueError(
                "sample_format must not be empty."
            )

        if (
            len(
                normalized
            )
            > STT_AUDIO_SAMPLE_FORMAT_MAX_CHARS
        ):
            raise ValueError(
                "sample_format is too long."
            )

        object.__setattr__(
            self,
            "sample_format",
            normalized,
        )


STTAudioConsumer: TypeAlias = Callable[
    [
        bytes,
        STTNativeAudioFormat,
    ],
    None,
]


@dataclass(
    frozen=True,
    slots=True,
)
class STTAudioHandoffObservation:
    """
    Privacy-minimized result of one handoff attempt.

    This object intentionally contains only byte count and native-format
    metadata. It never contains the raw payload.
    """

    status: STTAudioHandoffStatus
    byte_count: int
    audio_format: STTNativeAudioFormat
    reason: str

    authority: str = field(
        default=VOICE_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.status,
            STTAudioHandoffStatus,
        ):
            raise TypeError(
                "status must be STTAudioHandoffStatus."
            )

        if (
            type(
                self.byte_count
            )
            is not int
            or self.byte_count < 0
        ):
            raise ValueError(
                "byte_count must be a non-negative int."
            )

        if not isinstance(
            self.audio_format,
            STTNativeAudioFormat,
        ):
            raise TypeError(
                "audio_format must be STTNativeAudioFormat."
            )

        if not isinstance(
            self.reason,
            str,
        ):
            raise TypeError(
                "reason must be str."
            )

        normalized = (
            self.reason
            .strip()
        )

        if not normalized:
            raise ValueError(
                "reason must not be empty."
            )

        if (
            len(
                normalized
            )
            > STT_AUDIO_REASON_MAX_CHARS
        ):
            raise ValueError(
                "reason is too long."
            )

        object.__setattr__(
            self,
            "reason",
            normalized,
        )


def deliver_ephemeral_native_audio(
    payload: bytes,
    audio_format: STTNativeAudioFormat,
    consumer: STTAudioConsumer | None,
) -> STTAudioHandoffObservation:
    """
    Offer one native capture payload to a synchronous zero-authority consumer.

    The dispatcher retains no raw bytes and has no object state.

    Empty payloads and an absent consumer are normal no-op observations.
    Exceptions raised by a configured consumer are swallowed and represented
    as CONSUMER_ERROR so a future STT failure cannot redefine microphone
    capture truth.

    The consumer contract is intentionally synchronous at this seam. A future
    bounded STT process owner may copy/queue bytes under its own explicit
    bounded-lifetime contract; that behavior does not belong to STT-1A.
    """

    if type(
        payload
    ) is not bytes:
        raise TypeError(
            "payload must be bytes."
        )

    if not isinstance(
        audio_format,
        STTNativeAudioFormat,
    ):
        raise TypeError(
            "audio_format must be STTNativeAudioFormat."
        )

    byte_count = len(
        payload
    )

    if byte_count == 0:
        return STTAudioHandoffObservation(
            status=STTAudioHandoffStatus.EMPTY,
            byte_count=0,
            audio_format=audio_format,
            reason="empty native audio payload",
        )

    if consumer is None:
        return STTAudioHandoffObservation(
            status=STTAudioHandoffStatus.NO_CONSUMER,
            byte_count=byte_count,
            audio_format=audio_format,
            reason="no STT audio consumer configured",
        )

    if not callable(
        consumer
    ):
        raise TypeError(
            "consumer must be callable or None."
        )

    try:
        consumer(
            payload,
            audio_format,
        )
    except Exception:
        return STTAudioHandoffObservation(
            status=(
                STTAudioHandoffStatus.CONSUMER_ERROR
            ),
            byte_count=byte_count,
            audio_format=audio_format,
            reason="STT audio consumer failed",
        )

    return STTAudioHandoffObservation(
        status=STTAudioHandoffStatus.DELIVERED,
        byte_count=byte_count,
        audio_format=audio_format,
        reason="native audio delivered ephemerally",
    )
