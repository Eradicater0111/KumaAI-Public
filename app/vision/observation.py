from __future__ import annotations

from dataclasses import dataclass
import math
import secrets
import threading
import time


class ScreenObservationError(RuntimeError):
    """
    Raised when trusted screen-observation evidence is unavailable,
    malformed, stale, or no longer safe to use.
    """


@dataclass(frozen=True)
class ScreenObservation:
    """
    Immutable provenance for one real KUMA screen observation.

    Geometry comes from KUMA's capture/preparation pipeline.
    It is never supplied by the language model.
    """

    observation_id: str

    captured_at_monotonic: float

    capture_width: int
    capture_height: int

    vision_width: int
    vision_height: int

    native_width: int
    native_height: int

    vision_scale: float

    analysis: str

    def __str__(self) -> str:
        """
        Model-facing representation.

        The ID may be referenced by a future observation-bound
        click, but geometry remains trusted KUMA evidence.
        """

        return (
            "KUMA_SCREEN_OBSERVATION:\n"
            f"observation_id: {self.observation_id}\n"
            f"vision_size: {self.vision_width}x{self.vision_height}\n"
            "analysis:\n"
            f"{self.analysis}"
        )


class ScreenObservationStore:
    """
    Hold exactly one active screen observation.

    Safety properties:
    - newest observation replaces the previous one
    - observations expire from CAPTURE time, not analysis time
    - an observation may be claimed only once
    - stale observations fail closed
    - no model-provided geometry is stored
    """

    def __init__(
        self,
        *,
        max_age_seconds: float = 30.0,
    ):
        if (
            isinstance(max_age_seconds, bool)
            or not isinstance(
                max_age_seconds,
                (int, float),
            )
            or not math.isfinite(
                float(max_age_seconds)
            )
            or float(max_age_seconds) <= 0
        ):
            raise ValueError(
                "max_age_seconds must be a positive finite number."
            )

        self.max_age_seconds = float(
            max_age_seconds
        )

        self._active: ScreenObservation | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _positive_int(
        name: str,
        value: object,
    ) -> int:
        if (
            type(value) is not int
            or value <= 0
        ):
            raise ScreenObservationError(
                f"{name} must be a positive integer."
            )

        return value

    @staticmethod
    def _valid_analysis(
        analysis: object,
    ) -> str:
        if (
            type(analysis) is not str
            or not analysis.strip()
        ):
            raise ScreenObservationError(
                "Screen observation analysis is required."
            )

        return analysis.strip()

    @staticmethod
    def _valid_scale(
        scale: object,
    ) -> float:
        if (
            isinstance(scale, bool)
            or not isinstance(
                scale,
                (int, float),
            )
        ):
            raise ScreenObservationError(
                "Vision scale must be numeric."
            )

        scale = float(
            scale
        )

        if (
            not math.isfinite(scale)
            or scale <= 0
        ):
            raise ScreenObservationError(
                "Vision scale must be positive and finite."
            )

        return scale

    @staticmethod
    def _valid_timestamp(
        value: object,
    ) -> float:
        if (
            isinstance(value, bool)
            or not isinstance(
                value,
                (int, float),
            )
        ):
            raise ScreenObservationError(
                "Capture timestamp is invalid."
            )

        value = float(
            value
        )

        if not math.isfinite(
            value
        ):
            raise ScreenObservationError(
                "Capture timestamp must be finite."
            )

        return value

    @staticmethod
    def _aspect_ratio_close(
        *,
        capture_width: int,
        capture_height: int,
        native_width: int,
        native_height: int,
        tolerance: float = 0.01,
    ) -> bool:
        """
        Retina scaling may change absolute pixel counts but should
        preserve the same display rectangle/aspect ratio.

        A mismatch larger than 1% fails closed.
        """

        capture_ratio = (
            capture_width
            / capture_height
        )

        native_ratio = (
            native_width
            / native_height
        )

        relative_error = abs(
            capture_ratio
            - native_ratio
        ) / max(
            capture_ratio,
            native_ratio,
        )

        return (
            relative_error
            <= tolerance
        )

    def create(
        self,
        *,
        captured_at_monotonic: float,
        capture_width: int,
        capture_height: int,
        vision_width: int,
        vision_height: int,
        native_width: int,
        native_height: int,
        vision_scale: float,
        analysis: str,
    ) -> ScreenObservation:
        captured_at = (
            self._valid_timestamp(
                captured_at_monotonic
            )
        )

        capture_width = (
            self._positive_int(
                "capture_width",
                capture_width,
            )
        )

        capture_height = (
            self._positive_int(
                "capture_height",
                capture_height,
            )
        )

        vision_width = (
            self._positive_int(
                "vision_width",
                vision_width,
            )
        )

        vision_height = (
            self._positive_int(
                "vision_height",
                vision_height,
            )
        )

        native_width = (
            self._positive_int(
                "native_width",
                native_width,
            )
        )

        native_height = (
            self._positive_int(
                "native_height",
                native_height,
            )
        )

        scale = self._valid_scale(
            vision_scale
        )

        analysis = self._valid_analysis(
            analysis
        )

        if not self._aspect_ratio_close(
            capture_width=capture_width,
            capture_height=capture_height,
            native_width=native_width,
            native_height=native_height,
        ):
            raise ScreenObservationError(
                "Captured screen geometry does not match "
                "the native desktop rectangle."
            )

        observation = ScreenObservation(
            observation_id=(
                secrets.token_hex(16)
            ),
            captured_at_monotonic=(
                captured_at
            ),
            capture_width=(
                capture_width
            ),
            capture_height=(
                capture_height
            ),
            vision_width=(
                vision_width
            ),
            vision_height=(
                vision_height
            ),
            native_width=(
                native_width
            ),
            native_height=(
                native_height
            ),
            vision_scale=scale,
            analysis=analysis,
        )

        with self._lock:
            self._active = (
                observation
            )

        return observation

    def peek(
        self,
        observation_id: str,
        *,
        now: float | None = None,
    ) -> ScreenObservation:
        """
        Read the active observation without consuming it.

        Intended for validation only.
        """

        if (
            type(observation_id) is not str
            or not observation_id
        ):
            raise ScreenObservationError(
                "Observation ID is required."
            )

        current_time = (
            time.monotonic()
            if now is None
            else self._valid_timestamp(
                now
            )
        )

        with self._lock:
            observation = (
                self._active
            )

            if (
                observation is None
                or observation.observation_id
                != observation_id
            ):
                raise ScreenObservationError(
                    "Screen observation is unknown or no longer active."
                )

            age = (
                current_time
                - observation
                .captured_at_monotonic
            )

            if (
                age < 0
                or age
                > self.max_age_seconds
            ):
                self._active = None

                raise ScreenObservationError(
                    "Screen observation is stale."
                )

            return observation

    def claim(
        self,
        observation_id: str,
        *,
        now: float | None = None,
    ) -> ScreenObservation:
        """
        Atomically consume one active observation.

        A claimed observation cannot authorize another physical action.
        """

        observation = self.peek(
            observation_id,
            now=now,
        )

        with self._lock:
            if (
                self._active is None
                or self._active.observation_id
                != observation.observation_id
            ):
                raise ScreenObservationError(
                    "Screen observation was already consumed."
                )

            self._active = None

        return observation

    def clear(self) -> None:
        with self._lock:
            self._active = None


SCREEN_OBSERVATIONS = (
    ScreenObservationStore()
)
