"""Process-local provenance for one active screen observation.

This module stores immutable desktop evidence linked to an exact
ScreenObservation ID. It does not collect desktop state, call models, touch
screen stores, grant permission, or execute GUI actions.
"""

from dataclasses import dataclass
import math
import threading
import time

from app.desktop.contracts import DesktopContextObservation
from app.desktop.screen_binding import DesktopScreenBinding


def _finite_nonnegative(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


@dataclass(frozen=True)
class ScreenDesktopProvenance:
    """Historical desktop evidence for one exact trusted screen observation."""

    binding: DesktopScreenBinding
    desktop_before: DesktopContextObservation
    desktop_after: DesktopContextObservation

    def __post_init__(self):
        if type(self.binding) is not DesktopScreenBinding:
            raise ValueError("A trusted desktop-screen binding is required.")
        if (
            type(self.desktop_before) is not DesktopContextObservation
            or type(self.desktop_after) is not DesktopContextObservation
        ):
            raise ValueError("Trusted desktop source observations are required.")

        before = self.desktop_before
        after = self.desktop_after
        binding = self.binding

        if (
            before.observation_id != binding.desktop_before_id
            or after.observation_id != binding.desktop_after_id
            or before.captured_at_monotonic != binding.desktop_before_captured_at
            or after.captured_at_monotonic != binding.desktop_after_captured_at
            or before.status != binding.desktop_before_status
            or after.status != binding.desktop_after_status
            or before.diagnostics != binding.desktop_before_diagnostics
            or after.diagnostics != binding.desktop_after_diagnostics
        ):
            raise ValueError("Desktop sources do not match the binding exactly.")

        left = before.active_application
        right = after.active_application
        if (
            left is None
            or right is None
            or left.pid != binding.application_pid
            or right.pid != binding.application_pid
            or left.bundle_id != binding.application_bundle_id
            or right.bundle_id != binding.application_bundle_id
        ):
            raise ValueError("Desktop application identity does not match the binding.")


class ScreenDesktopProvenanceStore:
    """Hold provenance for exactly one active screen observation.

    Reads are exact by screen observation ID. There is deliberately no
    "latest good" fallback API. Expired evidence disappears and a clock
    failure clears the active record.
    """

    def __init__(self, *, clock=time.monotonic):
        if not callable(clock):
            raise TypeError("clock must be callable.")
        self._clock = clock
        self._active: ScreenDesktopProvenance | None = None
        self._last_now: float | None = None
        self._lock = threading.Lock()

    def _now(self):
        try:
            now = self._clock()
        except Exception:
            self._active = None
            raise ValueError("Provenance clock is unavailable.") from None
        if (
            not _finite_nonnegative(now)
            or (self._last_now is not None and now < self._last_now)
        ):
            self._active = None
            raise ValueError("Provenance clock is invalid or moved backward.")
        self._last_now = float(now)
        return float(now)

    def publish(self, provenance: ScreenDesktopProvenance) -> bool:
        if type(provenance) is not ScreenDesktopProvenance:
            raise TypeError("Expected ScreenDesktopProvenance.")
        with self._lock:
            now = self._now()
            if not provenance.binding.is_fresh(now):
                self._active = None
                return False
            self._active = provenance
            return True

    def get(self, screen_observation_id: str) -> ScreenDesktopProvenance | None:
        if type(screen_observation_id) is not str:
            raise TypeError("screen_observation_id must be a string.")
        with self._lock:
            now = self._now()
            active = self._active
            if active is None:
                return None
            if not active.binding.is_fresh(now):
                self._active = None
                return None
            if active.binding.screen_observation_id != screen_observation_id:
                return None
            return active

    def clear(self) -> None:
        with self._lock:
            self._active = None


SCREEN_DESKTOP_PROVENANCE = ScreenDesktopProvenanceStore()
