"""
KUMA-AVATAR-1D — bounded expressive visual mechanics projection.

This module converts device-independent AvatarSnapshot fields into renderer-
facing presentation parameters. It has no Qt, QML, desktop geometry, targeting,
tool, permission, execution, memory, model, or cognitive authority.

Boundaries:
- VISUAL GAZE != DESKTOP TARGET
- GAZE POSE != TARGET IDENTITY
- MOTION ENERGY != COGNITIVE ENERGY
- EXPRESSION INTENSITY != FACT CONFIDENCE
- VISUAL PARAMETERS != AUTHORITY
- RENDER MECHANICS != EXECUTION

AvatarGaze.TARGET is a fixed presentation pose only. It never carries or
derives a screen coordinate, accessibility element, pointer position, or
action target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math

from app.ui.avatar_runtime import (
    AVATAR_AUTHORITY_NONE,
    AvatarGaze,
    AvatarSnapshot,
)


AVATAR_VISUAL_AUTHORITY_NONE = AVATAR_AUTHORITY_NONE
AVATAR_GAZE_YAW_LIMIT_DEGREES = 8.0
AVATAR_GAZE_PITCH_LIMIT_DEGREES = 3.0

_GAZE_POSES = {
    AvatarGaze.FORWARD: (0.0, 0.0),
    AvatarGaze.USER: (0.0, -1.5),
    AvatarGaze.TARGET: (6.0, -1.0),
    AvatarGaze.AWAY: (-8.0, 2.0),
}


def _bounded_unit(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number.")

    normalized = float(value)

    if (
        not math.isfinite(normalized)
        or normalized < 0.0
        or normalized > 1.0
    ):
        raise ValueError(
            f"{name} must be finite and within [0.0, 1.0]."
        )

    return normalized


def _bounded_degrees(
    value: object,
    *,
    name: str,
    limit: float,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number.")

    normalized = float(value)

    if (
        not math.isfinite(normalized)
        or normalized < -limit
        or normalized > limit
    ):
        raise ValueError(
            f"{name} must be finite and within [-{limit}, {limit}]."
        )

    return normalized


@dataclass(frozen=True, slots=True)
class AvatarVisualParameters:
    """Immutable zero-authority renderer-facing presentation mechanics."""

    motion_energy: float = 0.0
    expression_intensity: float = 0.0
    gaze_yaw_degrees: float = 0.0
    gaze_pitch_degrees: float = 0.0
    authority: str = field(
        default=AVATAR_VISUAL_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "motion_energy",
            _bounded_unit(
                self.motion_energy,
                name="motion_energy",
            ),
        )
        object.__setattr__(
            self,
            "expression_intensity",
            _bounded_unit(
                self.expression_intensity,
                name="expression_intensity",
            ),
        )
        object.__setattr__(
            self,
            "gaze_yaw_degrees",
            _bounded_degrees(
                self.gaze_yaw_degrees,
                name="gaze_yaw_degrees",
                limit=AVATAR_GAZE_YAW_LIMIT_DEGREES,
            ),
        )
        object.__setattr__(
            self,
            "gaze_pitch_degrees",
            _bounded_degrees(
                self.gaze_pitch_degrees,
                name="gaze_pitch_degrees",
                limit=AVATAR_GAZE_PITCH_LIMIT_DEGREES,
            ),
        )


def project_avatar_visual_parameters(
    snapshot: AvatarSnapshot,
) -> AvatarVisualParameters:
    """
    Project one semantic AvatarSnapshot into bounded presentation mechanics.

    Gaze is categorical and maps to one fixed renderer pose. No coordinates or
    target identity are accepted or derived.
    """

    if not isinstance(snapshot, AvatarSnapshot):
        raise TypeError("snapshot must be AvatarSnapshot.")

    gaze_yaw, gaze_pitch = _GAZE_POSES[snapshot.gaze]

    return AvatarVisualParameters(
        motion_energy=snapshot.motion_energy,
        expression_intensity=snapshot.expression_intensity,
        gaze_yaw_degrees=gaze_yaw,
        gaze_pitch_degrees=gaze_pitch,
    )
