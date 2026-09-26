"""Exact-ID, process-local storage for one focused UI observation.

This store retains read-only focus evidence only. It performs no collection,
native AX access, target matching, permission decision, keyboard action, or
physical execution.

A newer unavailable focus observation replaces older available evidence so
failed recollection can never expose stale "last known good" focus.
"""

from __future__ import annotations

import math
import threading
import time
from typing import Callable

from app.ui_observation.focus_contracts import (
    FocusedUIObservation,
)


MAX_FOCUS_OBSERVATION_TTL_SECONDS = 60.0


def _finite_number(value):
    if type(value) not in (int, float):
        return False

    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class FocusedUIObservationStore:
    """Retain at most one fresh immutable focus observation by exact ID.

    There is deliberately no ``latest()`` API. Callers must already possess
    the exact focus-observation ID they intend to use.

    A newer accepted observation, including unavailable evidence, atomically
    replaces the previous active record. Reads never extend lifetime.

    ``clear()`` invalidates active evidence while preserving capture and clock
    high-water marks so older focus observations cannot become replayable.
    """

    def __init__(
        self,
        *,
        ttl_seconds=5.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        if (
            not _finite_number(ttl_seconds)
            or not 0.05
            <= ttl_seconds
            <= MAX_FOCUS_OBSERVATION_TTL_SECONDS
        ):
            raise ValueError(
                "ttl_seconds must be finite and between 0.05 and 60."
            )

        if not callable(clock):
            raise TypeError(
                "clock must be callable."
            )

        self._ttl = float(
            ttl_seconds
        )
        self._clock = clock
        self._lock = threading.Lock()

        self._active: FocusedUIObservation | None = None
        self._last_capture: float | None = None
        self._last_now: float | None = None

    def _clear_active(
        self,
    ) -> None:
        self._active = None

    def _now(
        self,
    ) -> float:
        try:
            now = self._clock()

            if (
                not _finite_number(now)
                or now < 0
                or (
                    self._last_now is not None
                    and now < self._last_now
                )
            ):
                raise ValueError(
                    "Invalid clock."
                )

        except Exception:
            self._clear_active()

            raise ValueError(
                "Focused UI store clock is unavailable, "
                "invalid, or moved backward."
            ) from None

        self._last_now = float(
            now
        )

        return float(
            now
        )

    def _expire(
        self,
        now: float,
    ) -> None:
        active = self._active

        if active is None:
            return

        if (
            now
            - active.captured_at_monotonic
            >= self._ttl
        ):
            self._clear_active()

    def publish(
        self,
        observation: FocusedUIObservation,
    ) -> bool:
        """Publish one fresh strictly newer focus observation."""

        if type(observation) is not FocusedUIObservation:
            raise TypeError(
                "Expected a FocusedUIObservation."
            )

        with self._lock:
            now = self._now()

            self._expire(
                now
            )

            captured = (
                observation.captured_at_monotonic
            )

            if captured > now:
                raise ValueError(
                    "Focus observation capture time is in the future."
                )

            if (
                now - captured
                >= self._ttl
            ):
                return False

            active = self._active

            if (
                active is not None
                and active.observation_id
                == observation.observation_id
            ):
                return False

            if (
                self._last_capture is not None
                and captured <= self._last_capture
            ):
                return False

            self._active = observation
            self._last_capture = captured

            return True

    def get(
        self,
        observation_id: str,
    ) -> FocusedUIObservation | None:
        """Return only the fresh active observation with this exact ID."""

        if type(observation_id) is not str:
            raise TypeError(
                "observation_id must be a string."
            )

        with self._lock:
            self._expire(
                self._now()
            )

            active = self._active

            if (
                active is None
                or active.observation_id
                != observation_id
            ):
                return None

            return active

    def clear(
        self,
    ) -> None:
        """Discard active evidence without resetting replay high-water marks."""

        with self._lock:
            self._clear_active()

    def __len__(
        self,
    ) -> int:
        with self._lock:
            self._expire(
                self._now()
            )

            return (
                1
                if self._active is not None
                else 0
            )


FOCUSED_UI_OBSERVATIONS = (
    FocusedUIObservationStore()
)
