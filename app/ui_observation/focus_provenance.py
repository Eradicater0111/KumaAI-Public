"""Exact in-memory provenance for one desktop-bound focused UI observation.

A FocusDesktopProvenance preserves the exact object graph produced by the
trusted 8D1 focus workflow:

    desktop-before
        +
    focused UI observation
        +
    desktop-after
        +
    DesktopFocusBinding

The provenance store accepts an entry only while the exact focused observation
object remains active in the corresponding FocusedUIObservationStore.

An equal reconstructed FocusedUIObservation is not the same source object and
cannot satisfy that requirement.

This module grants no text authority, target authority, permission, keyboard
authority, or physical execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import threading
import time

from app.desktop.contracts import (
    DesktopContextObservation,
)
from app.ui_observation.focus_binding import (
    DesktopFocusBinding,
)
from app.ui_observation.focus_contracts import (
    FOCUS_STATUS_AVAILABLE,
    FocusedUIObservation,
)
from app.ui_observation.focus_store import (
    FOCUSED_UI_OBSERVATIONS,
    FocusedUIObservationStore,
)


def _finite_nonnegative(
    value,
):
    return (
        type(value) in (
            int,
            float,
        )
        and math.isfinite(
            value
        )
        and value >= 0
    )


@dataclass(frozen=True)
class FocusDesktopProvenance:
    """Exact historical object graph for one trusted focus collection."""

    binding: DesktopFocusBinding = field(
        repr=False
    )

    focus_observation: FocusedUIObservation = field(
        repr=False
    )

    desktop_before: DesktopContextObservation = field(
        repr=False
    )

    desktop_after: DesktopContextObservation = field(
        repr=False
    )

    def __post_init__(
        self,
    ):
        if type(
            self.binding
        ) is not DesktopFocusBinding:
            raise ValueError(
                "Exact DesktopFocusBinding is required."
            )

        if type(
            self.focus_observation
        ) is not FocusedUIObservation:
            raise ValueError(
                "Exact FocusedUIObservation is required."
            )

        if (
            type(self.desktop_before)
            is not DesktopContextObservation
            or type(self.desktop_after)
            is not DesktopContextObservation
        ):
            raise ValueError(
                "Exact desktop source observations are required."
            )

        binding = self.binding
        focus = self.focus_observation
        before = self.desktop_before
        after = self.desktop_after

        if (
            binding.focus_observation_id
            != focus.observation_id
            or binding.focus_captured_at
            != focus.captured_at_monotonic
            or binding.focus_status
            != focus.status
            or binding.focus_diagnostics
            != focus.diagnostics
        ):
            raise ValueError(
                "Focus observation does not match its binding exactly."
            )

        if (
            before.observation_id
            != binding.desktop_before_id
            or before.captured_at_monotonic
            != binding.desktop_before_captured_at
            or before.status
            != binding.desktop_before_status
            or before.diagnostics
            != binding.desktop_before_diagnostics
        ):
            raise ValueError(
                "Desktop-before source does not match the binding exactly."
            )

        if (
            after.observation_id
            != binding.desktop_after_id
            or after.captured_at_monotonic
            != binding.desktop_after_captured_at
            or after.status
            != binding.desktop_after_status
            or after.diagnostics
            != binding.desktop_after_diagnostics
        ):
            raise ValueError(
                "Desktop-after source does not match the binding exactly."
            )

        if (
            focus.status
            != FOCUS_STATUS_AVAILABLE
        ):
            raise ValueError(
                "Focus provenance requires available focus evidence."
            )

        left = (
            before.active_application
        )

        middle = (
            focus.active_application
        )

        right = (
            after.active_application
        )

        if (
            left is None
            or middle is None
            or right is None
        ):
            raise ValueError(
                "Focus provenance requires complete application identity."
            )

        if not (
            left.pid
            == middle.pid
            == right.pid
            == binding.application_pid
            and left.bundle_id
            == middle.bundle_id
            == right.bundle_id
            == binding.application_bundle_id
        ):
            raise ValueError(
                "Focus provenance application identity does not "
                "match the exact binding."
            )

    @property
    def focus_observation_id(
        self,
    ):
        return (
            self.focus_observation.observation_id
        )

    @property
    def application_pid(
        self,
    ):
        return (
            self.binding.application_pid
        )

    @property
    def application_bundle_id(
        self,
    ):
        return (
            self.binding.application_bundle_id
        )

    def is_fresh(
        self,
        now,
    ):
        return (
            self.binding.is_fresh(
                now
            )
        )


class FocusDesktopProvenanceError(
    RuntimeError
):
    """Raised when exact active focus provenance cannot be trusted."""


class FocusDesktopProvenanceStore:
    """Retain provenance for exactly one active focus observation.

    There is deliberately no ``latest()`` API.

    Reads require the exact focus observation ID and additionally require the
    exact FocusedUIObservation object stored in the provenance to still be the
    active object in the associated focus-evidence store.

    Equal-value reconstruction does not satisfy object identity.
    """

    def __init__(
        self,
        *,
        focus_store=FOCUSED_UI_OBSERVATIONS,
        clock=time.monotonic,
    ):
        if type(
            focus_store
        ) is not FocusedUIObservationStore:
            raise TypeError(
                "focus_store must be a FocusedUIObservationStore."
            )

        if not callable(
            clock
        ):
            raise TypeError(
                "clock must be callable."
            )

        self._focus_store = (
            focus_store
        )

        self._clock = clock

        self._active: (
            FocusDesktopProvenance | None
        ) = None

        self._last_now: (
            float | None
        ) = None

        self._lock = (
            threading.Lock()
        )

    def _clear_active(
        self,
    ):
        self._active = None

    def _now(
        self,
    ):
        try:
            now = self._clock()
        except Exception:
            self._clear_active()

            raise FocusDesktopProvenanceError(
                "Focus provenance clock is unavailable."
            ) from None

        if (
            not _finite_nonnegative(
                now
            )
            or (
                self._last_now is not None
                and now < self._last_now
            )
        ):
            self._clear_active()

            raise FocusDesktopProvenanceError(
                "Focus provenance clock is invalid or moved backward."
            )

        self._last_now = float(
            now
        )

        return float(
            now
        )

    def _sources_are_current(
        self,
        provenance,
        now,
    ):
        if not provenance.is_fresh(
            now
        ):
            return False

        try:
            active_focus = (
                self._focus_store.get(
                    provenance.focus_observation_id
                )
            )
        except Exception:
            return False

        return (
            active_focus
            is provenance.focus_observation
        )

    def publish(
        self,
        provenance,
    ):
        if type(
            provenance
        ) is not FocusDesktopProvenance:
            raise TypeError(
                "Expected FocusDesktopProvenance."
            )

        with self._lock:
            now = self._now()

            if not self._sources_are_current(
                provenance,
                now,
            ):
                self._clear_active()
                return False

            self._active = (
                provenance
            )

            return True

    def get(
        self,
        focus_observation_id,
    ):
        if type(
            focus_observation_id
        ) is not str:
            raise TypeError(
                "focus_observation_id must be a string."
            )

        with self._lock:
            now = self._now()

            active = self._active

            if (
                active is None
                or active.focus_observation_id
                != focus_observation_id
            ):
                return None

            if not self._sources_are_current(
                active,
                now,
            ):
                self._clear_active()
                return None

            return active

    def clear(
        self,
    ):
        with self._lock:
            self._clear_active()

    def __len__(
        self,
    ):
        with self._lock:
            now = self._now()

            active = self._active

            if active is None:
                return 0

            if not self._sources_are_current(
                active,
                now,
            ):
                self._clear_active()
                return 0

            return 1


FOCUS_DESKTOP_PROVENANCE = (
    FocusDesktopProvenanceStore()
)
