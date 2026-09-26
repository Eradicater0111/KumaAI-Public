from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KumaExpressionMode(str, Enum):
    NEUTRAL = "neutral"
    WARM = "warm"
    HAPPY = "happy"
    PLAYFUL = "playful"
    ENERGETIC = "energetic"
    CURIOUS = "curious"
    GENTLE = "gentle"
    FOCUSED = "focused"
    ALERT = "alert"


class KumaGesture(str, Enum):
    NONE = "none"

    WAVE = "wave"

    OPEN_ARM = "open_arm"

    DOUBLE_ARM_LIFT = (
        "double_arm_lift"
    )

    CURIOUS_TILT = (
        "curious_tilt"
    )

    GENTLE_OPEN = (
        "gentle_open"
    )

    NOD = "nod"

    ATTENTIVE = "attentive"


@dataclass(
    frozen=True,
    slots=True,
)
class KumaExpressionDirective:
    """
    Presentation-level instruction for KUMA's body.

    This object describes how KUMA should visually
    respond to conversational affect.

    It contains no agent or tool authority.
    """

    mode: KumaExpressionMode = (
        KumaExpressionMode.NEUTRAL
    )

    gesture: KumaGesture = (
        KumaGesture.NONE
    )

    head_tilt_deg: float = 0.0

    bounce: float = 0.0

    pod_energy: float = 0.25

    motion_scale: float = 1.0

    hold_ms: int = 1800

    def __post_init__(
        self,
    ):
        object.__setattr__(
            self,
            "head_tilt_deg",
            max(
                -15.0,
                min(
                    15.0,
                    float(
                        self.head_tilt_deg
                    ),
                ),
            ),
        )

        object.__setattr__(
            self,
            "bounce",
            max(
                0.0,
                min(
                    1.0,
                    float(
                        self.bounce
                    ),
                ),
            ),
        )

        object.__setattr__(
            self,
            "pod_energy",
            max(
                0.0,
                min(
                    1.0,
                    float(
                        self.pod_energy
                    ),
                ),
            ),
        )

        object.__setattr__(
            self,
            "motion_scale",
            max(
                0.40,
                min(
                    1.60,
                    float(
                        self.motion_scale
                    ),
                ),
            ),
        )

        object.__setattr__(
            self,
            "hold_ms",
            max(
                250,
                min(
                    8000,
                    int(
                        self.hold_ms
                    ),
                ),
            ),
        )
