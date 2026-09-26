from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class KumaEmotion(str, Enum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    EXCITED = "excited"
    PLAYFUL = "playful"
    CURIOUS = "curious"
    GENTLE = "gentle"
    SAD = "sad"
    TIRED = "tired"
    CONFUSED = "confused"
    ALERT = "alert"
    FRUSTRATED = "frustrated"


class KumaTone(str, Enum):
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    PLAYFUL = "playful"
    ENERGETIC = "energetic"
    SUBDUED = "subdued"
    CURIOUS = "curious"
    SERIOUS = "serious"
    URGENT = "urgent"


@dataclass(
    frozen=True,
    slots=True,
)
class EmotionSignal:
    """
    Conversational affect inferred from language.

    This represents signals expressed by the user.
    It is not a claim about the user's internal
    psychological or medical state.
    """

    primary: KumaEmotion = (
        KumaEmotion.NEUTRAL
    )

    tone: KumaTone = (
        KumaTone.NEUTRAL
    )

    intensity: float = 0.0

    valence: float = 0.0

    urgency: float = 0.0

    confidence: float = 0.0

    @staticmethod
    def clamp(
        value,
    ) -> float:
        return max(
            0.0,
            min(
                1.0,
                float(value),
            ),
        )

    def __post_init__(
        self,
    ):
        object.__setattr__(
            self,
            "intensity",
            self.clamp(
                self.intensity
            ),
        )

        object.__setattr__(
            self,
            "urgency",
            self.clamp(
                self.urgency
            ),
        )

        object.__setattr__(
            self,
            "confidence",
            self.clamp(
                self.confidence
            ),
        )

        object.__setattr__(
            self,
            "valence",
            max(
                -1.0,
                min(
                    1.0,
                    float(
                        self.valence
                    ),
                ),
            ),
        )
