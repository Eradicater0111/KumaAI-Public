"""Read-only current desktop-context revalidation for Phase 7.4A5.

This module compares already-collected trusted desktop evidence. It does not
collect context, touch screen stores, call models, grant permission, or execute
GUI actions. A successful match is evidence only, never action authority.

Current A3 bindings identify the frontmost application (PID + bundle ID), not a
specific window. This module therefore proves application continuity only. It
must not claim focused-window continuity from window order, titles, or geometry.
"""

from dataclasses import dataclass
import math
import time

from app.desktop.contracts import DesktopContextObservation, MAX_TEXT
from app.desktop.screen_binding import DesktopScreenBinding


MAX_CURRENT_CONTEXT_AGE_SECONDS = 5.0

REVALIDATION_STATUSES = frozenset({
    "matched",
    "mismatch",
    "unknown",
})

REVALIDATION_CODES = frozenset({
    "clock_unavailable",
    "invalid_binding",
    "invalid_source_context",
    "binding_source_mismatch",
    "binding_expired",
    "current_context_unavailable",
    "current_application_identity_incomplete",
    "current_context_not_newer",
    "current_context_from_future",
    "current_context_stale",
    "current_context_reused",
    "application_changed",
})

MATCH_DIAGNOSTICS = frozenset({
    "source_context_partial",
    "current_context_partial",
})


def _finite_nonnegative(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _identifier(value):
    return (
        type(value) is str
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


def _bundle_id(value):
    return (
        type(value) is str
        and 0 < len(value) <= MAX_TEXT
        and bool(value.strip())
    )


@dataclass(frozen=True)
class DesktopContextRevalidation:
    """Immutable evidence that one fresh desktop sample matched a binding.

    This record says only that the current frontmost application's native PID
    and exact bundle ID matched the application identity recorded by the A3
    binding at check time. It does not prove focused-window identity, pixel
    continuity, screen-store liveness, semantic target validity, or permission
    to execute an action.
    """

    screen_observation_id: str
    desktop_before_id: str
    desktop_after_id: str
    current_desktop_observation_id: str
    application_pid: int
    application_bundle_id: str
    current_captured_at_monotonic: float
    checked_at_monotonic: float
    expires_at_monotonic: float
    source_context_partial: bool = False
    current_context_partial: bool = False

    def __post_init__(self):
        if not all(_identifier(value) for value in (
            self.screen_observation_id,
            self.desktop_before_id,
            self.desktop_after_id,
            self.current_desktop_observation_id,
        )):
            raise ValueError("Revalidation IDs must be canonical observation IDs.")

        if len({
            self.desktop_before_id,
            self.desktop_after_id,
            self.current_desktop_observation_id,
        }) != 3:
            raise ValueError("Revalidation requires distinct desktop observations.")

        if type(self.application_pid) is not int or self.application_pid <= 0:
            raise ValueError("Invalid application PID.")

        if not _bundle_id(self.application_bundle_id):
            raise ValueError("Complete application identity is required.")

        times = (
            self.current_captured_at_monotonic,
            self.checked_at_monotonic,
            self.expires_at_monotonic,
        )
        if not all(_finite_nonnegative(value) for value in times):
            raise ValueError("Revalidation times must be finite and nonnegative.")

        captured, checked, expiry = times
        if not captured <= checked < expiry:
            raise ValueError("Revalidation timing is invalid.")

        if (
            type(self.source_context_partial) is not bool
            or type(self.current_context_partial) is not bool
        ):
            raise ValueError("Partial-evidence flags must be booleans.")

    def is_fresh(self, now):
        """Check recorded lifetime only; never recollect or grant authority."""
        return (
            _finite_nonnegative(now)
            and self.checked_at_monotonic <= now < self.expires_at_monotonic
        )


@dataclass(frozen=True)
class DesktopContextRevalidationResult:
    status: str
    revalidation: DesktopContextRevalidation | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            type(self.status) is not str
            or self.status not in REVALIDATION_STATUSES
            or type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Invalid revalidation result.")

        if self.status == "matched":
            if type(self.revalidation) is not DesktopContextRevalidation:
                raise ValueError("Matched revalidation requires immutable evidence.")
            if any(code not in MATCH_DIAGNOSTICS for code in self.diagnostics):
                raise ValueError("Matched diagnostics must describe partial evidence only.")

            expected = []
            if self.revalidation.source_context_partial:
                expected.append("source_context_partial")
            if self.revalidation.current_context_partial:
                expected.append("current_context_partial")
            if self.diagnostics != tuple(expected):
                raise ValueError("Matched diagnostics must preserve source integrity.")
            return

        if self.revalidation is not None:
            raise ValueError("Unmatched revalidation cannot contain match evidence.")

        if (
            len(self.diagnostics) != 1
            or self.diagnostics[0] not in REVALIDATION_CODES
        ):
            raise ValueError("Unknown/mismatch results require one structured code.")

        if self.status == "mismatch":
            if self.diagnostics != ("application_changed",):
                raise ValueError("Only exact application change is a deterministic mismatch.")
        elif self.diagnostics == ("application_changed",):
            raise ValueError("Application change must be reported as mismatch.")

    @property
    def matched(self):
        return self.status == "matched" and self.revalidation is not None


def revalidate_desktop_context(
    binding,
    desktop_before,
    desktop_after,
    current,
    *,
    clock=time.monotonic,
    max_current_age_seconds=1.0,
):
    """Compare a fresh trusted desktop sample with an existing A3 binding.

    All observations must already come from trusted callers. No collection is
    performed here. Current A3 bindings carry application identity only, so
    success proves frontmost-application continuity, not window continuity.
    """

    def reject(status, code):
        return DesktopContextRevalidationResult(
            status=status,
            diagnostics=(code,),
        )

    if not callable(clock):
        raise TypeError("clock must be callable.")

    if (
        type(max_current_age_seconds) not in (int, float)
        or not math.isfinite(max_current_age_seconds)
        or not 0.05 <= max_current_age_seconds <= MAX_CURRENT_CONTEXT_AGE_SECONDS
    ):
        raise ValueError(
            "max_current_age_seconds must be finite and between 0.05 and 5."
        )

    if type(binding) is not DesktopScreenBinding:
        return reject("unknown", "invalid_binding")

    if (
        type(desktop_before) is not DesktopContextObservation
        or type(desktop_after) is not DesktopContextObservation
        or type(current) is not DesktopContextObservation
    ):
        return reject("unknown", "invalid_source_context")

    try:
        now = clock()
    except Exception:
        return reject("unknown", "clock_unavailable")

    if not _finite_nonnegative(now):
        return reject("unknown", "clock_unavailable")

    if not binding.is_fresh(now):
        return reject("unknown", "binding_expired")

    if (
        desktop_before.observation_id != binding.desktop_before_id
        or desktop_after.observation_id != binding.desktop_after_id
    ):
        return reject("unknown", "binding_source_mismatch")

    if (
        desktop_before.status == "unavailable"
        or desktop_after.status == "unavailable"
    ):
        return reject("unknown", "invalid_source_context")

    left = desktop_before.active_application
    right = desktop_after.active_application

    if (
        left is None
        or right is None
        or not _bundle_id(left.bundle_id)
        or not _bundle_id(right.bundle_id)
        or left.pid != binding.application_pid
        or right.pid != binding.application_pid
        or left.bundle_id != binding.application_bundle_id
        or right.bundle_id != binding.application_bundle_id
    ):
        return reject("unknown", "binding_source_mismatch")

    if current.observation_id in {
        binding.desktop_before_id,
        binding.desktop_after_id,
    }:
        return reject("unknown", "current_context_reused")

    if current.status == "unavailable":
        return reject("unknown", "current_context_unavailable")

    app = current.active_application
    if app is None or not _bundle_id(app.bundle_id):
        return reject("unknown", "current_application_identity_incomplete")

    captured = current.captured_at_monotonic
    if captured > now:
        return reject("unknown", "current_context_from_future")

    # A revalidation sample must begin only after the A3 binding itself existed.
    # This prevents reuse of an older desktop observation as "current" evidence.
    if captured < binding.bound_at_monotonic:
        return reject("unknown", "current_context_not_newer")

    if now - captured >= max_current_age_seconds:
        return reject("unknown", "current_context_stale")

    if (
        app.pid != binding.application_pid
        or app.bundle_id != binding.application_bundle_id
    ):
        return reject("mismatch", "application_changed")

    expiry = min(
        binding.expires_at_monotonic,
        captured + float(max_current_age_seconds),
    )
    if now >= expiry:
        return reject("unknown", "current_context_stale")

    source_partial = (
        desktop_before.status == "partial"
        or desktop_after.status == "partial"
    )
    current_partial = current.status == "partial"

    evidence = DesktopContextRevalidation(
        screen_observation_id=binding.screen_observation_id,
        desktop_before_id=binding.desktop_before_id,
        desktop_after_id=binding.desktop_after_id,
        current_desktop_observation_id=current.observation_id,
        application_pid=binding.application_pid,
        application_bundle_id=binding.application_bundle_id,
        current_captured_at_monotonic=captured,
        checked_at_monotonic=now,
        expires_at_monotonic=expiry,
        source_context_partial=source_partial,
        current_context_partial=current_partial,
    )

    diagnostics = []
    if source_partial:
        diagnostics.append("source_context_partial")
    if current_partial:
        diagnostics.append("current_context_partial")

    return DesktopContextRevalidationResult(
        status="matched",
        revalidation=evidence,
        diagnostics=tuple(diagnostics),
    )
