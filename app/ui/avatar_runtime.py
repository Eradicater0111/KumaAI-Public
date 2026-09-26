"""
KUMA-AVATAR-1A — zero-authority avatar runtime contract.

This module defines the semantic presentation state that KUMA may hand to an
avatar renderer. It intentionally does not know about QML geometry, ear angles,
blink timing, hover amplitudes, paint operations, audio playback, model calls,
tools, permissions, execution, memory, networking, or device control.

Critical boundaries:
- AVATAR STATE != COGNITIVE STATE
- AVATAR EXPRESSION != FACT
- AVATAR ATTENTION != PERMISSION
- SPEAKING != AUTHORITY
- ANIMATION != ACTION
- PRESENTATION != EXECUTION

Every object in this module remains AUTHORITY:NONE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math


AVATAR_AUTHORITY_NONE = "NONE"
_MAX_REASON_CHARS = 512


class AvatarMode(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ATTENTION = "attention"
    SUCCESS = "success"
    ERROR = "error"
    SLEEP = "sleep"


class AvatarExpression(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    FOCUSED = "focused"
    ALERT = "alert"
    GENTLE = "gentle"


class AvatarGaze(str, Enum):
    FORWARD = "forward"
    USER = "user"
    TARGET = "target"
    AWAY = "away"


def _bounded_scalar(value: object, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{field_name} must be a real number.")

    normalized = float(value)

    if (
        not math.isfinite(normalized)
        or normalized < 0.0
        or normalized > 1.0
    ):
        raise ValueError(
            f"{field_name} must be finite and within [0.0, 1.0]."
        )

    return normalized


def _reason(value: object) -> str:
    if type(value) is not str:
        raise TypeError("reason must be a string.")

    normalized = " ".join(value.split())

    if len(normalized) > _MAX_REASON_CHARS:
        raise ValueError(
            "reason exceeds the bounded avatar metadata limit."
        )

    return normalized


@dataclass(frozen=True, slots=True)
class AvatarSnapshot:
    """
    Immutable zero-authority snapshot of KUMA's presentation state.

    The snapshot is descriptive/presentational only. It cannot grant
    permission, confirm an action, choose a tool, execute anything, verify
    reality, mutate memory, or change KUMA's reasoning control flow.
    """

    mode: AvatarMode = AvatarMode.IDLE
    expression: AvatarExpression = AvatarExpression.NEUTRAL
    expression_intensity: float = 0.0
    gaze: AvatarGaze = AvatarGaze.FORWARD
    motion_energy: float = 0.0
    speech_active: bool = False
    reason: str = ""
    authority: str = field(
        default=AVATAR_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.mode, AvatarMode):
            raise TypeError("mode must be AvatarMode.")

        if not isinstance(self.expression, AvatarExpression):
            raise TypeError("expression must be AvatarExpression.")

        object.__setattr__(
            self,
            "expression_intensity",
            _bounded_scalar(
                self.expression_intensity,
                field_name="expression_intensity",
            ),
        )

        if not isinstance(self.gaze, AvatarGaze):
            raise TypeError("gaze must be AvatarGaze.")

        object.__setattr__(
            self,
            "motion_energy",
            _bounded_scalar(
                self.motion_energy,
                field_name="motion_energy",
            ),
        )

        if type(self.speech_active) is not bool:
            raise TypeError("speech_active must be bool.")

        object.__setattr__(
            self,
            "reason",
            _reason(self.reason),
        )

        speaking = self.mode == AvatarMode.SPEAKING

        if speaking != self.speech_active:
            raise ValueError(
                "speech_active must be true exactly when mode is SPEAKING."
            )


def default_avatar_snapshot() -> AvatarSnapshot:
    """Return a fresh canonical idle presentation snapshot."""

    return AvatarSnapshot()
