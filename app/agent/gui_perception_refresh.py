"""B8K2 fresh structured-screen corroboration for one prior perception context.

This module consumes one exact B8K1 context and performs a NEW read-only screen +
Accessibility observation inside a NEW trusted desktop bracket. The fresh screen
uses the original trusted vision geometry so an already-proposed vision point can
be re-evaluated in the same coordinate space without trusting model-supplied
geometry.

The result is evidence only. It does not resolve a semantic target, call a model,
grant permission, authorize GUI arguments, issue target attestations, assign
``semantic_target_verified``, or execute a physical action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

from app.agent.gui_perception_context import (
    CONTEXT_STATUS_AVAILABLE,
    STRUCTURED_UI_SCREEN_CONTEXTS,
    StructuredUIScreenPerceptionContext,
    StructuredUIScreenPerceptionContextStore,
    publish_structured_ui_screen_context,
)
from app.desktop.contracts import DesktopContextObservation
from app.desktop.provenance import (
    SCREEN_DESKTOP_PROVENANCE,
    ScreenDesktopProvenance,
)
from app.desktop.screen_binding import (
    bracket_desktop_capture,
    finalize_screen_binding,
)
from app.ui_observation.contracts import StructuredUIObservation
from app.vision.observation import (
    SCREEN_OBSERVATIONS,
    ScreenObservation,
)


BOOTSTRAP_STATUS_AVAILABLE = "available"
BOOTSTRAP_STATUS_UNKNOWN = "unknown"

BOOTSTRAP_UNKNOWN_CODES = frozenset({
    "invalid_context_store",
    "clock_unavailable",
    "desktop_before_unavailable",
    "application_identity_incomplete",
    "desktop_capture_access_uncertain",
    "screen_capture_unavailable",
    "structured_ui_unavailable",
    "desktop_after_unavailable",
    "application_identity_changed",
    "screen_binding_unavailable",
    "screen_analysis_unavailable",
    "screen_observation_unavailable",
    "screen_provenance_unavailable",
    "screen_provenance_publication_failed",
    "context_publication_failed",
})


@dataclass(frozen=True)
class StructuredUIScreenBootstrapResult:
    """One newly collected trusted B8K1 structured-screen context."""

    status: str
    context: StructuredUIScreenPerceptionContext | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if self.status not in {
            BOOTSTRAP_STATUS_AVAILABLE,
            BOOTSTRAP_STATUS_UNKNOWN,
        }:
            raise ValueError(
                "Invalid structured-screen bootstrap status."
            )

        if self.status == BOOTSTRAP_STATUS_AVAILABLE:
            if (
                type(self.context)
                is not StructuredUIScreenPerceptionContext
            ):
                raise ValueError(
                    "Available bootstrap requires exact context."
                )
            if self.diagnostics:
                raise ValueError(
                    "Available bootstrap cannot carry diagnostics."
                )
            return

        if self.context is not None:
            raise ValueError(
                "Unknown bootstrap cannot carry trusted context."
            )

        if (
            len(self.diagnostics) != 1
            or self.diagnostics[0]
            not in BOOTSTRAP_UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown bootstrap requires one structured diagnostic."
            )

    @property
    def available(self):
        return (
            self.status == BOOTSTRAP_STATUS_AVAILABLE
            and self.context is not None
        )



REFRESH_STATUS_AVAILABLE = "available"
REFRESH_STATUS_UNKNOWN = "unknown"
VALID_REFRESH_STATUSES = frozenset({
    REFRESH_STATUS_AVAILABLE,
    REFRESH_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "invalid_context_store",
    "invalid_screen_observation_id",
    "original_context_unavailable",
    "clock_unavailable",
    "desktop_before_unavailable",
    "application_identity_incomplete",
    "application_identity_changed",
    "screen_capture_unavailable",
    "screen_geometry_changed",
    "structured_ui_unavailable",
    "desktop_after_unavailable",
    "desktop_capture_access_uncertain",
    "screen_binding_unavailable",
    "screen_observation_unavailable",
    "screen_provenance_unavailable",
    "screen_provenance_publication_failed",
    "fresh_context_unavailable",
    "fresh_evidence_reused",
    "fresh_evidence_not_newer",
    "original_context_expired",
    "invalid_refresh_contract",
})


INTERNAL_FRESH_ANALYSIS = (
    "INTERNAL_FRESH_STRUCTURED_CORROBORATION_ONLY"
)


class StructuredUIScreenRefreshError(RuntimeError):
    """Raised only for malformed direct use of B8K2 refresh evidence."""


def _timestamp(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _same_application(left, right):
    return (
        left is not None
        and right is not None
        and type(left.pid) is int
        and type(right.pid) is int
        and left.pid == right.pid
        and type(left.bundle_id) is str
        and type(right.bundle_id) is str
        and bool(left.bundle_id.strip())
        and left.bundle_id == right.bundle_id
    )


def _complete_application(observation):
    if type(observation) is not DesktopContextObservation:
        return None
    app = observation.active_application
    if (
        app is None
        or type(app.pid) is not int
        or app.pid <= 0
        or type(app.bundle_id) is not str
        or not app.bundle_id.strip()
    ):
        return None
    return app


def _desktop_capture_access_uncertain(context):
    return bool(
        {
            "screen_capture_access_unavailable",
            "screen_capture_access_unknown",
        }
        & set(getattr(context, "diagnostics", ()))
    )


def _context_ids(context):
    binding = context.structured_screen_binding
    return {
        binding.ui_observation_id,
        binding.screen_observation_id,
        binding.desktop_before_id,
        binding.desktop_after_id,
    }


def _screen_geometry(screen):
    return (
        screen.capture_width,
        screen.capture_height,
        screen.vision_width,
        screen.vision_height,
        screen.native_width,
        screen.native_height,
        screen.vision_scale,
    )


@dataclass(frozen=True)
class StructuredUIScreenFreshCorroboration:
    """Exact original/fresh B8K1 context pair from independent brackets."""

    original_context: StructuredUIScreenPerceptionContext = field(repr=False)
    fresh_context: StructuredUIScreenPerceptionContext = field(repr=False)
    refreshed_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.original_context) is not StructuredUIScreenPerceptionContext:
            raise ValueError("Refresh requires the exact original B8K1 context.")
        if type(self.fresh_context) is not StructuredUIScreenPerceptionContext:
            raise ValueError("Refresh requires the exact fresh B8K1 context.")
        if not all(_timestamp(value) for value in (
            self.refreshed_at_monotonic,
            self.expires_at_monotonic,
        )):
            raise ValueError("Refresh timestamps are invalid.")

        original = self.original_context
        fresh = self.fresh_context

        if not _same_application(
            original.structured_ui_observation.active_application,
            fresh.structured_ui_observation.active_application,
        ):
            raise ValueError("Application identity changed across refresh.")

        if _screen_geometry(original.screen_observation) != _screen_geometry(
            fresh.screen_observation
        ):
            raise ValueError("Fresh screen geometry changed from the model-visible space.")

        if _context_ids(original) & _context_ids(fresh):
            raise ValueError("Fresh corroboration reused prior evidence IDs.")

        if not (
            fresh.screen_observation.captured_at_monotonic
            > original.screen_observation.captured_at_monotonic
            and fresh.structured_ui_observation.captured_at_monotonic
            > original.structured_ui_observation.captured_at_monotonic
            and fresh.structured_screen_binding.linked_at_monotonic
            > original.structured_screen_binding.linked_at_monotonic
            and fresh.published_at_monotonic
            > original.published_at_monotonic
        ):
            raise ValueError("Fresh corroboration must be strictly newer.")

        expected_expiry = min(
            original.expires_at_monotonic,
            fresh.expires_at_monotonic,
        )
        if (
            self.expires_at_monotonic != expected_expiry
            or not original.is_fresh(self.refreshed_at_monotonic)
            or not fresh.is_fresh(self.refreshed_at_monotonic)
            or not self.refreshed_at_monotonic < self.expires_at_monotonic
        ):
            raise ValueError("Refresh lifetime must remain inside both contexts.")

        try:
            active_screen = SCREEN_OBSERVATIONS.peek(
                fresh.screen_observation_id,
                now=self.refreshed_at_monotonic,
            )
        except Exception as error:
            raise ValueError("Fresh screen source is no longer active.") from error
        if active_screen is not fresh.screen_observation:
            raise ValueError("Refresh requires the exact active fresh screen object.")

        try:
            provenance = SCREEN_DESKTOP_PROVENANCE.get(
                fresh.screen_observation_id
            )
        except Exception as error:
            raise ValueError("Fresh screen provenance is unavailable.") from error
        if provenance is not fresh.screen_provenance:
            raise ValueError("Refresh requires exact fresh screen provenance.")

    @property
    def original_observation(self):
        return self.original_context.structured_ui_observation

    @property
    def original_binding(self):
        return self.original_context.structured_screen_binding

    @property
    def fresh_observation(self):
        return self.fresh_context.structured_ui_observation

    @property
    def fresh_binding(self):
        return self.fresh_context.structured_screen_binding

    @property
    def original_screen_observation_id(self):
        return self.original_context.screen_observation_id

    @property
    def fresh_screen_observation_id(self):
        return self.fresh_context.screen_observation_id

    def is_fresh(self, now):
        return (
            _timestamp(now)
            and self.refreshed_at_monotonic <= now < self.expires_at_monotonic
            and self.original_context.is_fresh(now)
            and self.fresh_context.is_fresh(now)
        )


@dataclass(frozen=True)
class StructuredUIScreenFreshCorroborationResult:
    status: str
    corroboration: StructuredUIScreenFreshCorroboration | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_REFRESH_STATUSES:
            raise ValueError("Invalid structured-screen refresh status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Refresh diagnostics must be immutable and unique.")

        if self.status == REFRESH_STATUS_AVAILABLE:
            if type(self.corroboration) is not StructuredUIScreenFreshCorroboration:
                raise ValueError("Available refresh requires exact corroboration.")
            if self.diagnostics:
                raise ValueError("Available refresh has no local diagnostics.")
            return

        if self.corroboration is not None:
            raise ValueError("Unknown refresh cannot carry trusted evidence.")
        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown refresh requires one structured diagnostic.")

    @property
    def available(self):
        return (
            self.status == REFRESH_STATUS_AVAILABLE
            and self.corroboration is not None
        )


def bootstrap_structured_ui_screen_context(
    *,
    context_store=STRUCTURED_UI_SCREEN_CONTEXTS,
    clock=time.monotonic,
    desktop_collector=None,
    screen_capture=None,
    structured_ui_collector=None,
    native_screen_size=None,
    image_analyzer=None,
):
    """Collect and publish one trusted initial structured-screen context.

    This is a read-only bootstrap for actions such as trusted focused typing
    that have semantic UI intent but deliberately carry no model-supplied
    screen observation ID or pointer coordinates.

    The collection sequence mirrors the production screen-capture trust
    boundary:

        desktop-before
        -> screenshot
        -> structured Accessibility observation
        -> desktop-after
        -> trusted capture bracket
        -> production vision geometry analysis
        -> screen binding/provenance
        -> structured-screen context publication

    No semantic target is resolved here and no physical input is emitted.
    """

    if type(context_store) is not StructuredUIScreenPerceptionContextStore:
        return StructuredUIScreenBootstrapResult(
            status=BOOTSTRAP_STATUS_UNKNOWN,
            diagnostics=("invalid_context_store",),
        )

    if not callable(clock):
        raise TypeError(
            "clock must be callable."
        )

    def unknown(code):
        return StructuredUIScreenBootstrapResult(
            status=BOOTSTRAP_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    def clear_active_evidence():
        SCREEN_OBSERVATIONS.clear()
        SCREEN_DESKTOP_PROVENANCE.clear()

        try:
            context_store.clear()
        except Exception:
            pass

    # Bootstrap owns the active screen/provenance/context lane.
    # Never fall back to a previous/latest observation.
    clear_active_evidence()

    if desktop_collector is None:
        from app.desktop.runtime import (
            collect_desktop_context,
        )

        desktop_collector = (
            collect_desktop_context
        )

    if screen_capture is None:
        from app.vision.screen import (
            capture_screen,
        )

        screen_capture = capture_screen

    if structured_ui_collector is None:
        from app.ui_observation.runtime import (
            collect_structured_ui,
        )

        structured_ui_collector = (
            collect_structured_ui
        )

    if native_screen_size is None:
        import pyautogui

        native_screen_size = (
            pyautogui.size
        )

    if image_analyzer is None:
        # Deferred import deliberately avoids a module-load cycle.
        #
        # This is the exact production analyzer already used by
        # computer_tools' trusted screen observation path, preserving
        # Retina capture/native/vision coordinate semantics.
        from app.tools.computer_tools import (
            analyze_image,
        )

        image_analyzer = analyze_image

    # -----------------------------------------------------
    # DESKTOP BEFORE
    # -----------------------------------------------------

    try:
        before = desktop_collector(
            timeout_seconds=3.0,
            max_windows=32,
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "desktop_before_unavailable"
        )

    if (
        type(before) is not DesktopContextObservation
        or before.status == "unavailable"
    ):
        clear_active_evidence()
        return unknown(
            "desktop_before_unavailable"
        )

    before_app = _complete_application(
        before
    )

    if before_app is None:
        clear_active_evidence()
        return unknown(
            "application_identity_incomplete"
        )

    if _desktop_capture_access_uncertain(
        before
    ):
        clear_active_evidence()
        return unknown(
            "desktop_capture_access_uncertain"
        )

    # -----------------------------------------------------
    # SCREEN CAPTURE
    # -----------------------------------------------------

    try:
        image = screen_capture()
    except Exception:
        clear_active_evidence()
        return unknown(
            "screen_capture_unavailable"
        )

    try:
        captured_at = clock()
    except Exception:
        clear_active_evidence()
        return unknown(
            "clock_unavailable"
        )

    if not _timestamp(
        captured_at
    ):
        clear_active_evidence()
        return unknown(
            "clock_unavailable"
        )

    # -----------------------------------------------------
    # STRUCTURED UI FROM SAME APPLICATION
    # -----------------------------------------------------

    try:
        structured_ui = (
            structured_ui_collector(
                before_app,
                timeout_seconds=2.0,
                max_nodes=128,
                max_depth=6,
                max_children=32,
            )
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "structured_ui_unavailable"
        )

    if (
        type(structured_ui)
        is not StructuredUIObservation
        or structured_ui.status == "unavailable"
    ):
        clear_active_evidence()
        return unknown(
            "structured_ui_unavailable"
        )

    if not _same_application(
        before_app,
        structured_ui.active_application,
    ):
        clear_active_evidence()
        return unknown(
            "application_identity_changed"
        )

    # -----------------------------------------------------
    # DESKTOP AFTER
    # -----------------------------------------------------

    try:
        after = desktop_collector(
            timeout_seconds=3.0,
            max_windows=32,
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "desktop_after_unavailable"
        )

    if (
        type(after) is not DesktopContextObservation
        or after.status == "unavailable"
    ):
        clear_active_evidence()
        return unknown(
            "desktop_after_unavailable"
        )

    after_app = _complete_application(
        after
    )

    if after_app is None:
        clear_active_evidence()
        return unknown(
            "application_identity_incomplete"
        )

    if _desktop_capture_access_uncertain(
        after
    ):
        clear_active_evidence()
        return unknown(
            "desktop_capture_access_uncertain"
        )

    if not _same_application(
        before_app,
        after_app,
    ):
        clear_active_evidence()
        return unknown(
            "application_identity_changed"
        )

    # -----------------------------------------------------
    # TRUSTED CAPTURE BRACKET
    # -----------------------------------------------------

    try:
        bracket_result = (
            bracket_desktop_capture(
                captured_at,
                before,
                after,
                clock=clock,
                max_age_seconds=(
                    SCREEN_OBSERVATIONS
                    .max_age_seconds
                ),
                max_capture_gap_seconds=5.0,
            )
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "screen_binding_unavailable"
        )

    if not bracket_result.bracketed:
        clear_active_evidence()
        return unknown(
            "screen_binding_unavailable"
        )

    # -----------------------------------------------------
    # PRODUCTION SCREEN GEOMETRY
    # -----------------------------------------------------

    try:
        analysis = image_analyzer(
            image
        )

        native_width, native_height = (
            native_screen_size()
        )

        native_width = int(
            native_width
        )

        native_height = int(
            native_height
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "screen_analysis_unavailable"
        )

    # Do NOT derive these dimensions ourselves.
    #
    # Exact production semantics:
    #   capture_*  <- analyze_image()
    #   vision_*   <- analyze_image()
    #   vision_scale <- analyze_image()
    #   native_*   <- pyautogui.size()
    try:
        observation = (
            SCREEN_OBSERVATIONS.create(
                captured_at_monotonic=(
                    captured_at
                ),
                capture_width=(
                    analysis.capture_width
                ),
                capture_height=(
                    analysis.capture_height
                ),
                vision_width=(
                    analysis.vision_width
                ),
                vision_height=(
                    analysis.vision_height
                ),
                native_width=(
                    native_width
                ),
                native_height=(
                    native_height
                ),
                vision_scale=(
                    analysis.vision_scale
                ),
                analysis=(
                    analysis.analysis
                ),
            )
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "screen_observation_unavailable"
        )

    # -----------------------------------------------------
    # SCREEN ↔ DESKTOP PROVENANCE
    # -----------------------------------------------------

    try:
        binding_result = (
            finalize_screen_binding(
                observation,
                bracket_result.bracket,
                clock=clock,
            )
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "screen_binding_unavailable"
        )

    if not binding_result.linked:
        clear_active_evidence()
        return unknown(
            "screen_binding_unavailable"
        )

    try:
        provenance = (
            ScreenDesktopProvenance(
                binding=(
                    binding_result.binding
                ),
                desktop_before=before,
                desktop_after=after,
            )
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "screen_provenance_unavailable"
        )

    try:
        published = (
            SCREEN_DESKTOP_PROVENANCE
            .publish(
                provenance
            )
        )
    except Exception:
        published = False

    if not published:
        clear_active_evidence()
        return unknown(
            "screen_provenance_publication_failed"
        )

    # -----------------------------------------------------
    # B8K1 STRUCTURED-SCREEN CONTEXT
    # -----------------------------------------------------

    try:
        context_result = (
            publish_structured_ui_screen_context(
                observation,
                structured_ui,
                provenance,
                store=context_store,
                clock=clock,
            )
        )
    except Exception:
        clear_active_evidence()
        return unknown(
            "context_publication_failed"
        )

    if (
        context_result.status
        != CONTEXT_STATUS_AVAILABLE
        or not context_result.available
        or context_result.context is None
    ):
        clear_active_evidence()
        return unknown(
            "context_publication_failed"
        )

    return StructuredUIScreenBootstrapResult(
        status=(
            BOOTSTRAP_STATUS_AVAILABLE
        ),
        context=(
            context_result.context
        ),
    )



def refresh_structured_ui_screen_context(
    screen_observation_id,
    *,
    context_store=STRUCTURED_UI_SCREEN_CONTEXTS,
    clock=time.monotonic,
    desktop_collector=None,
    screen_capture=None,
    structured_ui_collector=None,
    native_screen_size=None,
):
    """Consume B8K1 context and collect one independent fresh context.

    Production callers omit the collector arguments. Tests may inject read-only
    stand-ins. The original context is consumed before any fresh collection, and
    every unsuccessful attempt clears screen/provenance/context state so no old
    or partially refreshed evidence remains usable.
    """

    if type(context_store) is not StructuredUIScreenPerceptionContextStore:
        return StructuredUIScreenFreshCorroborationResult(
            status=REFRESH_STATUS_UNKNOWN,
            diagnostics=("invalid_context_store",),
        )
    if not callable(clock):
        raise TypeError("clock must be callable.")
    if type(screen_observation_id) is not str or not screen_observation_id.strip():
        return StructuredUIScreenFreshCorroborationResult(
            status=REFRESH_STATUS_UNKNOWN,
            diagnostics=("invalid_screen_observation_id",),
        )
    screen_observation_id = screen_observation_id.strip()

    def unknown(code):
        return StructuredUIScreenFreshCorroborationResult(
            status=REFRESH_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    def clear_active_evidence():
        SCREEN_OBSERVATIONS.clear()
        SCREEN_DESKTOP_PROVENANCE.clear()
        try:
            context_store.clear()
        except Exception:
            pass

    try:
        original = context_store.claim(screen_observation_id)
    except Exception:
        clear_active_evidence()
        return unknown("original_context_unavailable")

    # Claim already verified exact active original sources. From this point on,
    # the global screen/provenance stores are reserved exclusively for fresh
    # evidence. Local ``original`` keeps the immutable historical graph.
    SCREEN_OBSERVATIONS.clear()
    SCREEN_DESKTOP_PROVENANCE.clear()

    if desktop_collector is None:
        from app.desktop.runtime import collect_desktop_context
        desktop_collector = collect_desktop_context
    if screen_capture is None:
        from app.vision.screen import capture_screen
        screen_capture = capture_screen
    if structured_ui_collector is None:
        from app.ui_observation.runtime import collect_structured_ui
        structured_ui_collector = collect_structured_ui
    if native_screen_size is None:
        import pyautogui
        native_screen_size = pyautogui.size

    try:
        before = desktop_collector(
            timeout_seconds=3.0,
            max_windows=32,
        )
    except Exception:
        clear_active_evidence()
        return unknown("desktop_before_unavailable")

    if type(before) is not DesktopContextObservation or before.status == "unavailable":
        clear_active_evidence()
        return unknown("desktop_before_unavailable")
    before_app = _complete_application(before)
    if before_app is None:
        clear_active_evidence()
        return unknown("application_identity_incomplete")
    if _desktop_capture_access_uncertain(before):
        clear_active_evidence()
        return unknown("desktop_capture_access_uncertain")
    if not _same_application(
        original.structured_ui_observation.active_application,
        before_app,
    ):
        clear_active_evidence()
        return unknown("application_identity_changed")

    try:
        image = screen_capture()
    except Exception:
        clear_active_evidence()
        return unknown("screen_capture_unavailable")

    try:
        captured_at = clock()
    except Exception:
        clear_active_evidence()
        return unknown("clock_unavailable")
    if not _timestamp(captured_at):
        clear_active_evidence()
        return unknown("clock_unavailable")

    try:
        capture_width, capture_height = image.size
        native_width, native_height = native_screen_size()
        capture_width = int(capture_width)
        capture_height = int(capture_height)
        native_width = int(native_width)
        native_height = int(native_height)
    except Exception:
        clear_active_evidence()
        return unknown("screen_geometry_changed")

    original_screen = original.screen_observation
    if (
        (capture_width, capture_height)
        != (original_screen.capture_width, original_screen.capture_height)
        or (native_width, native_height)
        != (original_screen.native_width, original_screen.native_height)
    ):
        clear_active_evidence()
        return unknown("screen_geometry_changed")

    try:
        fresh_ui = structured_ui_collector(
            before_app,
            timeout_seconds=2.0,
            max_nodes=128,
            max_depth=6,
            max_children=32,
        )
    except Exception:
        clear_active_evidence()
        return unknown("structured_ui_unavailable")

    if (
        type(fresh_ui) is not StructuredUIObservation
        or fresh_ui.status == "unavailable"
    ):
        clear_active_evidence()
        return unknown("structured_ui_unavailable")
    if not _same_application(before_app, fresh_ui.active_application):
        clear_active_evidence()
        return unknown("application_identity_changed")

    try:
        after = desktop_collector(
            timeout_seconds=3.0,
            max_windows=32,
        )
    except Exception:
        clear_active_evidence()
        return unknown("desktop_after_unavailable")

    if type(after) is not DesktopContextObservation or after.status == "unavailable":
        clear_active_evidence()
        return unknown("desktop_after_unavailable")
    after_app = _complete_application(after)
    if after_app is None:
        clear_active_evidence()
        return unknown("application_identity_incomplete")
    if _desktop_capture_access_uncertain(after):
        clear_active_evidence()
        return unknown("desktop_capture_access_uncertain")
    if not _same_application(before_app, after_app):
        clear_active_evidence()
        return unknown("application_identity_changed")

    try:
        bracket_result = bracket_desktop_capture(
            captured_at,
            before,
            after,
            clock=clock,
            max_age_seconds=SCREEN_OBSERVATIONS.max_age_seconds,
            max_capture_gap_seconds=5.0,
        )
    except Exception:
        clear_active_evidence()
        return unknown("screen_binding_unavailable")
    if not bracket_result.bracketed:
        clear_active_evidence()
        return unknown("screen_binding_unavailable")

    try:
        fresh_screen = SCREEN_OBSERVATIONS.create(
            captured_at_monotonic=captured_at,
            capture_width=capture_width,
            capture_height=capture_height,
            vision_width=original_screen.vision_width,
            vision_height=original_screen.vision_height,
            native_width=native_width,
            native_height=native_height,
            vision_scale=original_screen.vision_scale,
            analysis=INTERNAL_FRESH_ANALYSIS,
        )
    except Exception:
        clear_active_evidence()
        return unknown("screen_observation_unavailable")

    try:
        binding_result = finalize_screen_binding(
            fresh_screen,
            bracket_result.bracket,
            clock=clock,
        )
    except Exception:
        clear_active_evidence()
        return unknown("screen_binding_unavailable")
    if not binding_result.linked:
        clear_active_evidence()
        return unknown("screen_binding_unavailable")

    try:
        provenance = ScreenDesktopProvenance(
            binding=binding_result.binding,
            desktop_before=before,
            desktop_after=after,
        )
    except Exception:
        clear_active_evidence()
        return unknown("screen_provenance_unavailable")

    try:
        published = SCREEN_DESKTOP_PROVENANCE.publish(provenance)
    except Exception:
        published = False
    if not published:
        clear_active_evidence()
        return unknown("screen_provenance_publication_failed")

    # Build fresh K1 context in an isolated store. The global B8K1 store remains
    # consumed; B8K3 receives the exact returned pair rather than claiming a
    # second model-facing context token.
    try:
        local_context_store = StructuredUIScreenPerceptionContextStore(
            clock=clock
        )
        fresh_result = publish_structured_ui_screen_context(
            fresh_screen,
            fresh_ui,
            provenance,
            store=local_context_store,
            clock=clock,
        )
    except Exception:
        clear_active_evidence()
        return unknown("fresh_context_unavailable")

    if (
        fresh_result.status != CONTEXT_STATUS_AVAILABLE
        or not fresh_result.available
    ):
        clear_active_evidence()
        return unknown("fresh_context_unavailable")
    fresh = fresh_result.context

    original_ids = _context_ids(original)
    fresh_ids = _context_ids(fresh)
    if original_ids & fresh_ids:
        clear_active_evidence()
        return unknown("fresh_evidence_reused")

    if not (
        fresh.screen_observation.captured_at_monotonic
        > original.screen_observation.captured_at_monotonic
        and fresh.structured_ui_observation.captured_at_monotonic
        > original.structured_ui_observation.captured_at_monotonic
        and fresh.structured_screen_binding.linked_at_monotonic
        > original.structured_screen_binding.linked_at_monotonic
        and fresh.published_at_monotonic
        > original.published_at_monotonic
    ):
        clear_active_evidence()
        return unknown("fresh_evidence_not_newer")

    try:
        refreshed_at = clock()
    except Exception:
        clear_active_evidence()
        return unknown("clock_unavailable")
    if not _timestamp(refreshed_at):
        clear_active_evidence()
        return unknown("clock_unavailable")

    if not original.is_fresh(refreshed_at):
        clear_active_evidence()
        return unknown("original_context_expired")

    try:
        corroboration = StructuredUIScreenFreshCorroboration(
            original_context=original,
            fresh_context=fresh,
            refreshed_at_monotonic=refreshed_at,
            expires_at_monotonic=min(
                original.expires_at_monotonic,
                fresh.expires_at_monotonic,
            ),
        )
    except Exception:
        clear_active_evidence()
        return unknown("invalid_refresh_contract")

    return StructuredUIScreenFreshCorroborationResult(
        status=REFRESH_STATUS_AVAILABLE,
        corroboration=corroboration,
    )
