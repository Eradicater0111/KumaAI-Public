"""B8K1 trusted structured-screen perception context.

This module joins one already-trusted ScreenObservation and its exact native
Desktop provenance with one structured UI snapshot captured inside the same
desktop bracket. The resulting context preserves an exact in-memory object graph
for later B8K2 fresh corroboration.

The context is evidence only. It performs no UI collection, screen capture,
model call, permission decision, argument authorization, target attestation,
``semantic_target_verified`` assignment, or physical action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import threading
import time

from app.desktop.provenance import (
    SCREEN_DESKTOP_PROVENANCE,
    ScreenDesktopProvenance,
)
from app.ui_observation.contracts import StructuredUIObservation
from app.ui_observation.desktop_binding import (
    DesktopUIBinding,
    bind_desktop_to_structured_ui,
)
from app.ui_observation.screen_binding import (
    StructuredUIScreenBinding,
    bind_structured_ui_to_screen,
)
from app.vision.observation import (
    SCREEN_OBSERVATIONS,
    ScreenObservation,
    ScreenObservationError,
)


CONTEXT_STATUS_AVAILABLE = "available"
CONTEXT_STATUS_UNKNOWN = "unknown"
VALID_CONTEXT_STATUSES = frozenset({
    CONTEXT_STATUS_AVAILABLE,
    CONTEXT_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "invalid_store",
    "store_reset_failed",
    "invalid_screen_observation",
    "invalid_structured_ui_observation",
    "invalid_screen_provenance",
    "structured_ui_unavailable",
    "ui_binding_unavailable",
    "screen_binding_unavailable",
    "clock_unavailable",
    "context_publication_failed",
    "invalid_context_contract",
})


class StructuredUIScreenPerceptionContextError(RuntimeError):
    """Raised when exact B8K1 context evidence is unavailable or stale."""


def _timestamp(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


@dataclass(frozen=True)
class StructuredUIScreenPerceptionContext:
    """Exact same-bracket screen + AX evidence for one perception cycle."""

    screen_observation: ScreenObservation = field(repr=False)
    structured_ui_observation: StructuredUIObservation = field(repr=False)
    screen_provenance: ScreenDesktopProvenance = field(repr=False)
    ui_binding: DesktopUIBinding = field(repr=False)
    structured_screen_binding: StructuredUIScreenBinding = field(repr=False)
    published_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.screen_observation) is not ScreenObservation:
            raise ValueError("Context requires an exact ScreenObservation.")
        if type(self.structured_ui_observation) is not StructuredUIObservation:
            raise ValueError("Context requires an exact StructuredUIObservation.")
        if type(self.screen_provenance) is not ScreenDesktopProvenance:
            raise ValueError("Context requires exact screen-desktop provenance.")
        if type(self.ui_binding) is not DesktopUIBinding:
            raise ValueError("Context requires an exact desktop-UI binding.")
        if type(self.structured_screen_binding) is not StructuredUIScreenBinding:
            raise ValueError("Context requires an exact structured-screen binding.")

        if (
            self.structured_screen_binding.ui_binding is not self.ui_binding
            or self.structured_screen_binding.screen_provenance
            is not self.screen_provenance
        ):
            raise ValueError("Context requires one exact joined binding graph.")

        screen_binding = self.screen_provenance.binding
        if (
            screen_binding.screen_observation_id
            != self.screen_observation.observation_id
            or screen_binding.screen_captured_at
            != self.screen_observation.captured_at_monotonic
        ):
            raise ValueError("Screen observation does not match exact provenance.")

        ui = self.structured_ui_observation
        if (
            self.ui_binding.ui_observation_id != ui.observation_id
            or self.ui_binding.ui_captured_at != ui.captured_at_monotonic
            or self.ui_binding.ui_status != ui.status
            or self.ui_binding.ui_diagnostics != ui.diagnostics
        ):
            raise ValueError("Structured UI observation does not match exact binding.")

        app = ui.active_application
        if (
            app is None
            or app.pid != self.ui_binding.application_pid
            or app.bundle_id != self.ui_binding.application_bundle_id
        ):
            raise ValueError("Structured UI application identity does not match binding.")

        if not all(_timestamp(value) for value in (
            self.published_at_monotonic,
            self.expires_at_monotonic,
        )):
            raise ValueError("Context timestamps are invalid.")
        if (
            self.published_at_monotonic
            < self.structured_screen_binding.linked_at_monotonic
            or self.expires_at_monotonic
            != self.structured_screen_binding.expires_at_monotonic
            or not self.published_at_monotonic < self.expires_at_monotonic
        ):
            raise ValueError("Context lifetime must equal its exact joined evidence.")

    @property
    def screen_observation_id(self):
        return self.screen_observation.observation_id

    @property
    def ui_observation_id(self):
        return self.structured_ui_observation.observation_id

    @property
    def application_pid(self):
        return self.structured_screen_binding.application_pid

    @property
    def application_bundle_id(self):
        return self.structured_screen_binding.application_bundle_id

    def is_fresh(self, now):
        return (
            _timestamp(now)
            and self.published_at_monotonic <= now < self.expires_at_monotonic
            and self.structured_screen_binding.is_fresh(now)
        )


@dataclass(frozen=True)
class StructuredUIScreenPerceptionContextResult:
    status: str
    context: StructuredUIScreenPerceptionContext | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_CONTEXT_STATUSES:
            raise ValueError("Invalid structured-screen context status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Context diagnostics must be immutable and unique.")

        if self.status == CONTEXT_STATUS_AVAILABLE:
            if type(self.context) is not StructuredUIScreenPerceptionContext:
                raise ValueError("Available context requires exact evidence.")
            if self.diagnostics:
                raise ValueError("Available context has no local diagnostics.")
            return

        if self.context is not None:
            raise ValueError("Unknown context cannot carry trusted evidence.")
        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown context requires one structured diagnostic.")

    @property
    def available(self):
        return (
            self.status == CONTEXT_STATUS_AVAILABLE
            and self.context is not None
        )


class StructuredUIScreenPerceptionContextStore:
    """Hold one exact, short-lived B8K1 context by screen observation ID.

    ``claim`` consumes the active context on every attempt before validating the
    supplied ID. This prevents repeated ID probing and guarantees that later B8K2
    work starts from at most one original perception context.
    """

    def __init__(self, *, clock=time.monotonic):
        if not callable(clock):
            raise TypeError("clock must be callable.")
        self._clock = clock
        self._active: StructuredUIScreenPerceptionContext | None = None
        self._last_now: float | None = None
        self._lock = threading.Lock()

    def _now(self):
        try:
            now = self._clock()
        except Exception:
            self._active = None
            raise StructuredUIScreenPerceptionContextError(
                "Structured-screen context clock is unavailable."
            ) from None
        if (
            not _timestamp(now)
            or (self._last_now is not None and now < self._last_now)
        ):
            self._active = None
            raise StructuredUIScreenPerceptionContextError(
                "Structured-screen context clock is invalid or moved backward."
            )
        self._last_now = float(now)
        return float(now)

    @staticmethod
    def _validate_sources(context, now):
        try:
            active_screen = SCREEN_OBSERVATIONS.peek(
                context.screen_observation_id,
                now=now,
            )
        except ScreenObservationError as error:
            raise StructuredUIScreenPerceptionContextError(
                "Source screen observation is no longer active."
            ) from error
        if active_screen is not context.screen_observation:
            raise StructuredUIScreenPerceptionContextError(
                "Context requires the exact active screen object."
            )

        try:
            provenance = SCREEN_DESKTOP_PROVENANCE.get(
                context.screen_observation_id
            )
        except Exception as error:
            raise StructuredUIScreenPerceptionContextError(
                "Source screen provenance is unavailable."
            ) from error
        if provenance is not context.screen_provenance:
            raise StructuredUIScreenPerceptionContextError(
                "Context requires the exact active screen provenance object."
            )

    def publish(self, context):
        if type(context) is not StructuredUIScreenPerceptionContext:
            raise TypeError("Expected StructuredUIScreenPerceptionContext.")

        with self._lock:
            now = self._now()
            if not context.is_fresh(now):
                self._active = None
                return False
            try:
                self._validate_sources(context, now)
            except StructuredUIScreenPerceptionContextError:
                self._active = None
                return False
            self._active = context
            return True

    def peek(self, screen_observation_id):
        if type(screen_observation_id) is not str or not screen_observation_id:
            raise StructuredUIScreenPerceptionContextError(
                "Screen observation ID is required."
            )

        with self._lock:
            now = self._now()
            active = self._active
            if active is None or active.screen_observation_id != screen_observation_id:
                raise StructuredUIScreenPerceptionContextError(
                    "Structured-screen context is unknown or no longer active."
                )
            if not active.is_fresh(now):
                self._active = None
                raise StructuredUIScreenPerceptionContextError(
                    "Structured-screen context is stale."
                )
            try:
                self._validate_sources(active, now)
            except StructuredUIScreenPerceptionContextError:
                self._active = None
                raise
            return active

    def claim(self, screen_observation_id):
        if type(screen_observation_id) is not str or not screen_observation_id:
            raise StructuredUIScreenPerceptionContextError(
                "Screen observation ID is required."
            )

        with self._lock:
            now = self._now()
            active = self._active
            self._active = None

            if active is None:
                raise StructuredUIScreenPerceptionContextError(
                    "Structured-screen context is unavailable."
                )
            if active.screen_observation_id != screen_observation_id:
                raise StructuredUIScreenPerceptionContextError(
                    "Structured-screen context does not match the requested screen."
                )
            if not active.is_fresh(now):
                raise StructuredUIScreenPerceptionContextError(
                    "Structured-screen context is stale."
                )
            self._validate_sources(active, now)
            return active

    def clear(self):
        with self._lock:
            self._active = None


STRUCTURED_UI_SCREEN_CONTEXTS = StructuredUIScreenPerceptionContextStore()


def publish_structured_ui_screen_context(
    screen_observation,
    structured_ui_observation,
    screen_provenance,
    *,
    store=STRUCTURED_UI_SCREEN_CONTEXTS,
    clock=time.monotonic,
):
    """Bind and publish one same-bracket B8K1 context, fail closed.

    The caller is responsible for collecting the screen and structured UI
    snapshot inside the exact desktop bracket represented by
    ``screen_provenance``. This function only validates and joins those sources.
    """

    if type(store) is not StructuredUIScreenPerceptionContextStore:
        return StructuredUIScreenPerceptionContextResult(
            status=CONTEXT_STATUS_UNKNOWN,
            diagnostics=("invalid_store",),
        )
    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(code):
        return StructuredUIScreenPerceptionContextResult(
            status=CONTEXT_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    try:
        store.clear()
    except Exception:
        return unknown("store_reset_failed")

    if type(screen_observation) is not ScreenObservation:
        return unknown("invalid_screen_observation")
    if type(structured_ui_observation) is not StructuredUIObservation:
        return unknown("invalid_structured_ui_observation")
    if type(screen_provenance) is not ScreenDesktopProvenance:
        return unknown("invalid_screen_provenance")
    if structured_ui_observation.status == "unavailable":
        return unknown("structured_ui_unavailable")

    try:
        ui_binding_result = bind_desktop_to_structured_ui(
            structured_ui_observation,
            screen_provenance.desktop_before,
            screen_provenance.desktop_after,
            clock=clock,
            max_age_seconds=SCREEN_OBSERVATIONS.max_age_seconds,
            max_capture_gap_seconds=5.0,
        )
    except Exception:
        return unknown("ui_binding_unavailable")

    if not ui_binding_result.linked:
        return unknown("ui_binding_unavailable")

    try:
        screen_binding_result = bind_structured_ui_to_screen(
            ui_binding_result.binding,
            screen_provenance,
            clock=clock,
        )
    except Exception:
        return unknown("screen_binding_unavailable")

    if not screen_binding_result.linked:
        return unknown("screen_binding_unavailable")

    try:
        published_at = clock()
    except Exception:
        return unknown("clock_unavailable")
    if not _timestamp(published_at):
        return unknown("clock_unavailable")

    try:
        context = StructuredUIScreenPerceptionContext(
            screen_observation=screen_observation,
            structured_ui_observation=structured_ui_observation,
            screen_provenance=screen_provenance,
            ui_binding=ui_binding_result.binding,
            structured_screen_binding=screen_binding_result.binding,
            published_at_monotonic=published_at,
            expires_at_monotonic=(
                screen_binding_result.binding.expires_at_monotonic
            ),
        )
    except Exception:
        return unknown("invalid_context_contract")

    try:
        if not store.publish(context):
            return unknown("context_publication_failed")
    except Exception:
        return unknown("context_publication_failed")

    return StructuredUIScreenPerceptionContextResult(
        status=CONTEXT_STATUS_AVAILABLE,
        context=context,
    )
