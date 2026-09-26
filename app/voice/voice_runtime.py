"""
KUMA-VOICE-1A — zero-authority voice runtime contract.

This module defines immutable, device-independent voice presentation/I/O state.
It does not open a microphone, synthesize speech, play audio, transcribe audio,
call a model, invoke tools, access memory, request permission, or execute work.

Core boundaries:

- VOICE STATE != COGNITIVE STATE
- TRANSCRIPT != COMMAND AUTHORITY
- MICROPHONE ACTIVE != LISTENING ANIMATION
- LISTENING ANIMATION MUST FOLLOW REAL CAPTURE STATE
- PLAYBACK ACTIVE MUST FOLLOW REAL AUDIO PLAYBACK
- TTS OUTPUT != MODEL CONTROL
- VOICE ERROR != TASK FAILURE
- VOICE INPUT != PERMISSION
- VOICE != EXECUTION
- VOICE AUTHORITY = NONE

The contract is intentionally independent of Qt, audio providers, models,
agents, tools, memory, networking, and device-control implementations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re


VOICE_AUTHORITY_NONE = "NONE"

VOICE_REASON_MAX_CHARS = 512
VOICE_TRANSCRIPT_MAX_CHARS = 8192


class VoiceInputMode(str, Enum):
    """Observed microphone / speech-input lifecycle."""

    UNAVAILABLE = "unavailable"
    INACTIVE = "inactive"
    CAPTURING = "capturing"
    TRANSCRIBING = "transcribing"
    ERROR = "error"


class VoiceOutputMode(str, Enum):
    """Observed speech-output lifecycle."""

    IDLE = "idle"
    SYNTHESIZING = "synthesizing"
    PLAYING = "playing"
    ERROR = "error"


def _normalized_text(
    value: str,
    *,
    name: str,
    max_chars: int,
    allow_empty: bool,
) -> str:
    if type(value) is not str:
        raise TypeError(
            f"{name} must be str."
        )

    normalized = re.sub(
        r"\s+",
        " ",
        value,
    ).strip()

    if (
        not allow_empty
        and not normalized
    ):
        raise ValueError(
            f"{name} must not be empty."
        )

    if len(normalized) > max_chars:
        raise ValueError(
            f"{name} must be <= {max_chars} characters."
        )

    return normalized


@dataclass(
    frozen=True,
    slots=True,
)
class VoiceTranscript:
    """
    Immutable zero-authority speech-recognition result.

    A transcript is observed text only. It is not permission, confirmation,
    an executable command, a verified fact, or authority to bypass KUMA's
    existing action-safety boundaries.
    """

    text: str
    is_final: bool = True

    authority: str = field(
        default=VOICE_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        object.__setattr__(
            self,
            "text",
            _normalized_text(
                self.text,
                name="text",
                max_chars=(
                    VOICE_TRANSCRIPT_MAX_CHARS
                ),
                allow_empty=False,
            ),
        )

        if type(
            self.is_final
        ) is not bool:
            raise TypeError(
                "is_final must be bool."
            )


@dataclass(
    frozen=True,
    slots=True,
)
class VoiceSnapshot:
    """
    Immutable zero-authority snapshot of observable voice I/O state.

    microphone_active and playback_active are truth-bearing I/O flags:
    they must describe actual capture/playback state rather than UI intent,
    animation intent, model intent, or predicted future state.
    """

    input_mode: VoiceInputMode = (
        VoiceInputMode.UNAVAILABLE
    )

    output_mode: VoiceOutputMode = (
        VoiceOutputMode.IDLE
    )

    microphone_active: bool = False
    playback_active: bool = False

    transcript: VoiceTranscript | None = None

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

        if not isinstance(
            self.output_mode,
            VoiceOutputMode,
        ):
            raise TypeError(
                "output_mode must be VoiceOutputMode."
            )

        if type(
            self.microphone_active
        ) is not bool:
            raise TypeError(
                "microphone_active must be bool."
            )

        if type(
            self.playback_active
        ) is not bool:
            raise TypeError(
                "playback_active must be bool."
            )

        if (
            self.transcript is not None
            and not isinstance(
                self.transcript,
                VoiceTranscript,
            )
        ):
            raise TypeError(
                "transcript must be VoiceTranscript or None."
            )

        object.__setattr__(
            self,
            "reason",
            _normalized_text(
                self.reason,
                name="reason",
                max_chars=VOICE_REASON_MAX_CHARS,
                allow_empty=True,
            ),
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

        playing = (
            self.output_mode
            == VoiceOutputMode.PLAYING
        )

        if (
            playing
            != self.playback_active
        ):
            raise ValueError(
                "playback_active must be true exactly when "
                "output_mode is PLAYING."
            )


def idle_voice_snapshot() -> VoiceSnapshot:
    """
    Return a fresh neutral snapshot.

    Input defaults to UNAVAILABLE rather than pretending a microphone exists.
    """

    return VoiceSnapshot()
