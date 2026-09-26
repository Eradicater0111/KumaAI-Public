"""Exact-ID, process-local storage for one structured UI observation.

This store retains read-only evidence only. It never grants action authority,
performs collection, calls models, or falls back to an older successful tree.
"""

import math
import threading
import time
from typing import Callable

from app.ui_observation.contracts import StructuredUIObservation


MAX_UI_OBSERVATION_TTL_SECONDS = 60.0


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class StructuredUIObservationStore:
    """Retain at most one fresh immutable UI snapshot by exact identity.

    There is deliberately no ``latest()`` API. Callers must already possess
    the exact observation ID they intend to use. A newer accepted observation,
    including ``partial`` or ``unavailable`` evidence, replaces the previous
    record. Reads never refresh lifetime.

    ``clear()`` discards the active record but preserves capture/clock
    high-water marks so clearing cannot make an older snapshot replayable.
    """

    def __init__(
        self,
        *,
        ttl_seconds=5.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if (
            not _finite_number(ttl_seconds)
            or not 0.05 <= ttl_seconds <= MAX_UI_OBSERVATION_TTL_SECONDS
        ):
            raise ValueError(
                "ttl_seconds must be finite and between 0.05 and 60."
            )
        if not callable(clock):
            raise TypeError("clock must be callable.")

        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._active: StructuredUIObservation | None = None
        self._last_capture: float | None = None
        self._last_now: float | None = None

    def _clear_active(self) -> None:
        self._active = None

    def _now(self) -> float:
        try:
            now = self._clock()
            if (
                not _finite_number(now)
                or now < 0
                or (self._last_now is not None and now < self._last_now)
            ):
                raise ValueError("Invalid clock.")
        except Exception:
            self._clear_active()
            raise ValueError(
                "Structured UI store clock is unavailable, invalid, or moved backward."
            ) from None

        self._last_now = float(now)
        return float(now)

    def _expire(self, now: float) -> None:
        active = self._active
        if active is None:
            return
        if now - active.captured_at_monotonic >= self._ttl:
            self._clear_active()

    def publish(self, observation: StructuredUIObservation) -> bool:
        """Publish one fresh, strictly newer snapshot, or return ``False``.

        Successful publication atomically replaces the previous active record.
        Status is never promoted: ``partial`` and ``unavailable`` observations
        are retained exactly as supplied, preventing an older available tree
        from becoming an implicit fallback.
        """

        if type(observation) is not StructuredUIObservation:
            raise TypeError("Expected a StructuredUIObservation.")

        with self._lock:
            now = self._now()
            self._expire(now)

            captured = observation.captured_at_monotonic
            if captured > now:
                raise ValueError("Observation capture time is in the future.")
            if now - captured >= self._ttl:
                return False
            if self._last_capture is not None and captured <= self._last_capture:
                return False

            self._active = observation
            self._last_capture = captured
            return True

    def get(self, observation_id: str) -> StructuredUIObservation | None:
        """Return only the fresh active snapshot with this exact ID."""

        if type(observation_id) is not str:
            raise TypeError("observation_id must be a string.")

        with self._lock:
            self._expire(self._now())
            active = self._active
            if active is None or active.observation_id != observation_id:
                return None
            return active

    def clear(self) -> None:
        """Discard active evidence without resetting replay high-water marks."""

        with self._lock:
            self._clear_active()

    def __len__(self) -> int:
        with self._lock:
            self._expire(self._now())
            return 1 if self._active is not None else 0


STRUCTURED_UI_OBSERVATIONS = StructuredUIObservationStore()
