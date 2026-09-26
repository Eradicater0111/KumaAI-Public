"""Pure binding of one structured UI snapshot to bracketing desktop evidence.

A DesktopUIBinding is historical provenance only. It proves that one bounded
structured UI observation was captured while the same frontmost application
identity (native PID + exact bundle ID) was observed by trusted desktop
samples before and after it. It does not prove exact window identity, pixel
continuity, element stability, user intent, permission, or action authority.
"""

from dataclasses import dataclass, field
import math
import time

from app.desktop.contracts import (
    DesktopContextObservation,
    DIAGNOSTICS as DESKTOP_DIAGNOSTICS,
    MAX_TEXT,
)
from app.ui_observation.contracts import (
    DIAGNOSTICS as UI_DIAGNOSTICS,
    StructuredUIObservation,
)


MAX_UI_BINDING_AGE_SECONDS = 60.0
MAX_UI_BINDING_GAP_SECONDS = 5.0

REJECTION_CODES = frozenset({
    "clock_unavailable",
    "invalid_ui_metadata",
    "invalid_desktop_metadata",
    "desktop_context_unavailable",
    "structured_ui_unavailable",
    "application_identity_incomplete",
    "application_changed",
    "source_observations_not_distinct",
    "capture_order_invalid",
    "capture_gap_exceeded",
    "evidence_from_future",
    "evidence_expired",
})

MATCH_DIAGNOSTICS = frozenset({
    "desktop_context_partial",
    "structured_ui_partial",
})


def _timestamp(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _identifier(value):
    return (
        type(value) is str
        and len(value) == 32
        and all(character in "0123456789abcdef" for character in value)
    )


def _bundle(value):
    return (
        type(value) is str
        and 0 < len(value) <= MAX_TEXT
        and bool(value.strip())
    )


def _policy(max_age_seconds, max_capture_gap_seconds):
    return (
        _timestamp(max_age_seconds)
        and 0.05 <= max_age_seconds <= MAX_UI_BINDING_AGE_SECONDS
        and _timestamp(max_capture_gap_seconds)
        and 0 < max_capture_gap_seconds
        <= min(MAX_UI_BINDING_GAP_SECONDS, max_age_seconds)
    )


def _source_integrity(status, diagnostics, *, allowed_diagnostics, source_name):
    if type(status) is not str or status not in ("available", "partial"):
        raise ValueError(f"Unavailable {source_name} evidence cannot be linked.")
    if (
        type(diagnostics) is not tuple
        or any(
            type(code) is not str or code not in allowed_diagnostics
            for code in diagnostics
        )
        or len(set(diagnostics)) != len(diagnostics)
        or bool(diagnostics) != (status == "partial")
    ):
        raise ValueError(f"{source_name} diagnostics must preserve source integrity.")


def _match_diagnostics(before_status, after_status, ui_status):
    diagnostics = []
    if "partial" in (before_status, after_status):
        diagnostics.append("desktop_context_partial")
    if ui_status == "partial":
        diagnostics.append("structured_ui_partial")
    return tuple(diagnostics)


@dataclass(frozen=True)
class DesktopUIBinding:
    """Immutable provenance for one exact structured UI observation."""

    ui_observation_id: str
    desktop_before_id: str
    desktop_after_id: str
    application_pid: int
    application_bundle_id: str = field(repr=False)
    desktop_before_captured_at: float = 0.0
    ui_captured_at: float = 0.0
    desktop_after_captured_at: float = 0.0
    bound_at_monotonic: float = 0.0
    expires_at_monotonic: float = 0.0
    desktop_before_status: str = "available"
    desktop_after_status: str = "available"
    ui_status: str = "available"
    desktop_before_diagnostics: tuple[str, ...] = ()
    desktop_after_diagnostics: tuple[str, ...] = ()
    ui_diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        ids = (
            self.ui_observation_id,
            self.desktop_before_id,
            self.desktop_after_id,
        )
        if not all(_identifier(value) for value in ids):
            raise ValueError("Binding IDs must be canonical observation IDs.")
        if len(set(ids)) != 3:
            raise ValueError("UI and desktop source observations must be distinct.")
        if type(self.application_pid) is not int or self.application_pid <= 0:
            raise ValueError("Invalid application PID.")
        if not _bundle(self.application_bundle_id):
            raise ValueError("Complete application identity is required.")

        times = (
            self.desktop_before_captured_at,
            self.ui_captured_at,
            self.desktop_after_captured_at,
            self.bound_at_monotonic,
            self.expires_at_monotonic,
        )
        if not all(_timestamp(value) for value in times):
            raise ValueError("Binding times must be finite and nonnegative.")

        before, ui, after, bound, expiry = times
        if not (before <= ui <= after <= bound < expiry and before < after):
            raise ValueError("Binding capture order or expiry is invalid.")
        if (
            after - before > MAX_UI_BINDING_GAP_SECONDS
            or expiry - before > MAX_UI_BINDING_AGE_SECONDS
        ):
            raise ValueError("Binding interval exceeds its hard bounds.")

        _source_integrity(
            self.desktop_before_status,
            self.desktop_before_diagnostics,
            allowed_diagnostics=DESKTOP_DIAGNOSTICS,
            source_name="desktop",
        )
        _source_integrity(
            self.desktop_after_status,
            self.desktop_after_diagnostics,
            allowed_diagnostics=DESKTOP_DIAGNOSTICS,
            source_name="desktop",
        )
        _source_integrity(
            self.ui_status,
            self.ui_diagnostics,
            allowed_diagnostics=UI_DIAGNOSTICS,
            source_name="structured UI",
        )

    def is_fresh(self, now):
        """Check recorded lifetime only; never recollect or grant authority."""
        return (
            _timestamp(now)
            and self.bound_at_monotonic <= now < self.expires_at_monotonic
        )


@dataclass(frozen=True)
class DesktopUIBindingResult:
    binding: DesktopUIBinding | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Diagnostics must be immutable and unique.")

        if self.binding is None:
            if (
                len(self.diagnostics) != 1
                or self.diagnostics[0] not in REJECTION_CODES
            ):
                raise ValueError("Failed binding requires one structured rejection code.")
            return

        if type(self.binding) is not DesktopUIBinding:
            raise ValueError("Invalid desktop-UI binding evidence.")
        if any(code not in MATCH_DIAGNOSTICS for code in self.diagnostics):
            raise ValueError("Successful diagnostics may describe partial evidence only.")

        expected = _match_diagnostics(
            self.binding.desktop_before_status,
            self.binding.desktop_after_status,
            self.binding.ui_status,
        )
        if self.diagnostics != expected:
            raise ValueError("Diagnostics must preserve source integrity.")

    @property
    def linked(self):
        return self.binding is not None


def bind_desktop_to_structured_ui(
    ui_observation,
    desktop_before,
    desktop_after,
    *,
    clock=time.monotonic,
    max_age_seconds=5.0,
    max_capture_gap_seconds=3.0,
):
    """Bind one UI snapshot to exact bracketing desktop observations.

    No collection, model, store, screen capture, AX action, permission check, or
    execution occurs here. Titles, application names, element text, and AX
    paths do not establish application identity; only native PID + bundle ID do.
    """

    if not _policy(max_age_seconds, max_capture_gap_seconds):
        raise ValueError("Invalid desktop-UI binding age or capture-gap policy.")
    if not callable(clock):
        raise TypeError("clock must be callable.")

    def reject(code):
        return DesktopUIBindingResult(diagnostics=(code,))

    try:
        now = clock()
    except Exception:
        return reject("clock_unavailable")
    if not _timestamp(now):
        return reject("clock_unavailable")

    if type(ui_observation) is not StructuredUIObservation:
        return reject("invalid_ui_metadata")
    if (
        type(desktop_before) is not DesktopContextObservation
        or type(desktop_after) is not DesktopContextObservation
    ):
        return reject("invalid_desktop_metadata")

    if desktop_before.status == "unavailable" or desktop_after.status == "unavailable":
        return reject("desktop_context_unavailable")
    if ui_observation.status == "unavailable":
        return reject("structured_ui_unavailable")

    left = desktop_before.active_application
    middle = ui_observation.active_application
    right = desktop_after.active_application

    if (
        left is None
        or middle is None
        or right is None
        or not _bundle(left.bundle_id)
        or not _bundle(middle.bundle_id)
        or not _bundle(right.bundle_id)
    ):
        return reject("application_identity_incomplete")

    if not (
        left.pid == middle.pid == right.pid
        and left.bundle_id == middle.bundle_id == right.bundle_id
    ):
        return reject("application_changed")

    ids = (
        ui_observation.observation_id,
        desktop_before.observation_id,
        desktop_after.observation_id,
    )
    if len(set(ids)) != 3:
        return reject("source_observations_not_distinct")

    before = desktop_before.captured_at_monotonic
    ui_captured = ui_observation.captured_at_monotonic
    after = desktop_after.captured_at_monotonic

    if max(before, ui_captured, after) > now:
        return reject("evidence_from_future")
    if not (before <= ui_captured <= after and before < after):
        return reject("capture_order_invalid")
    if after - before > max_capture_gap_seconds:
        return reject("capture_gap_exceeded")

    expiry = before + max_age_seconds
    if now >= expiry:
        return reject("evidence_expired")

    binding = DesktopUIBinding(
        ui_observation_id=ui_observation.observation_id,
        desktop_before_id=desktop_before.observation_id,
        desktop_after_id=desktop_after.observation_id,
        application_pid=left.pid,
        application_bundle_id=left.bundle_id,
        desktop_before_captured_at=before,
        ui_captured_at=ui_captured,
        desktop_after_captured_at=after,
        bound_at_monotonic=now,
        expires_at_monotonic=expiry,
        desktop_before_status=desktop_before.status,
        desktop_after_status=desktop_after.status,
        ui_status=ui_observation.status,
        desktop_before_diagnostics=desktop_before.diagnostics,
        desktop_after_diagnostics=desktop_after.diagnostics,
        ui_diagnostics=ui_observation.diagnostics,
    )

    return DesktopUIBindingResult(
        binding=binding,
        diagnostics=_match_diagnostics(
            desktop_before.status,
            desktop_after.status,
            ui_observation.status,
        ),
    )
