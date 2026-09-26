"""Bounded, process-local observation storage. This is never action authority."""

from collections import OrderedDict
import math
import threading
import time
from typing import Callable

from app.desktop.contracts import DesktopContextObservation


MAX_STORE_CAPACITY = 256
MAX_TTL_SECONDS = 60.0


def _finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


class DesktopContextStore:
    """Retain immutable observations until capture-time expiry.

    Reads never extend lifetime. A newer unavailable observation remains the
    latest result; callers never silently fall back to earlier available data.
    This class neither collects context nor connects to execution services.
    """

    def __init__(self, *, capacity=32, ttl_seconds=5.0,
                 clock: Callable[[], float] = time.monotonic):
        if type(capacity) is not int or not 1 <= capacity <= MAX_STORE_CAPACITY:
            raise ValueError(f"capacity must be an integer from 1 to {MAX_STORE_CAPACITY}.")
        if not _finite_number(ttl_seconds) or not 0.05 <= ttl_seconds <= MAX_TTL_SECONDS:
            raise ValueError("ttl_seconds must be finite and between 0.05 and 60.")
        if not callable(clock):
            raise TypeError("clock must be callable.")
        self._capacity = capacity
        self._ttl = float(ttl_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._observations = OrderedDict()
        self._latest_id = None
        self._last_capture = None
        self._last_now = None

    def _clear_records(self):
        self._observations.clear()
        self._latest_id = None
        self._last_capture = None

    def _now(self):
        try:
            now = self._clock()
            if (not _finite_number(now) or now < 0
                    or (self._last_now is not None and now < self._last_now)):
                raise ValueError("Invalid clock.")
        except Exception:
            self._clear_records()
            raise ValueError("Store clock is unavailable, invalid, or moved backward.") from None
        self._last_now = now
        return now

    def _expire(self, now):
        # Accepted capture times are strictly increasing, so expiry is ordered.
        while self._observations:
            observation = next(iter(self._observations.values()))
            if now - observation.captured_at_monotonic < self._ttl:
                break
            self._observations.popitem(last=False)
        # Retain latest ID and capture high-water mark: expiry must not cause
        # fallback or allow an older observation to become the latest result.

    def put(self, observation: DesktopContextObservation) -> bool:
        """Accept a fresh, strictly newer capture, or return False.

        Duplicate resident IDs, expired captures, and captures no newer than
        the last accepted timestamp are refused. Future timestamps are errors.
        No ID rewrite, status promotion, or observation mutation is performed.
        """
        if type(observation) is not DesktopContextObservation:
            raise TypeError("Expected a DesktopContextObservation.")
        with self._lock:
            now = self._now()
            self._expire(now)
            captured = observation.captured_at_monotonic
            if captured > now:
                raise ValueError("Observation capture time is in the future.")
            if (now - captured >= self._ttl
                    or observation.observation_id in self._observations
                    or (self._last_capture is not None and captured <= self._last_capture)):
                return False
            self._observations[observation.observation_id] = observation
            self._latest_id = observation.observation_id
            self._last_capture = captured
            while len(self._observations) > self._capacity:
                self._observations.popitem(last=False)
            return True

    def get(self, observation_id: str) -> DesktopContextObservation | None:
        """Read an unexpired resident observation by ID without refreshing it."""
        if type(observation_id) is not str:
            raise TypeError("observation_id must be a string.")
        with self._lock:
            self._expire(self._now())
            return self._observations.get(observation_id)

    def latest(self) -> DesktopContextObservation | None:
        """Return the latest accepted observation, or None after expiry/clear."""
        with self._lock:
            self._expire(self._now())
            return self._observations.get(self._latest_id)

    def clear(self) -> None:
        """Discard records and capture ordering; preserve clock monotonicity."""
        with self._lock:
            self._clear_records()

    def __len__(self) -> int:
        with self._lock:
            self._expire(self._now())
            return len(self._observations)
