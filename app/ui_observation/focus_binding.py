"""Pure desktop provenance binding for one native focus observation.

A DesktopFocusBinding proves only that one exact FocusedUIObservation was
captured while independently trusted desktop observations before and after it
reported the same native application PID and exact bundle ID.

It does not prove stable AX identity across snapshots, semantic target identity,
focused-window identity, user intent, text authority, permission, keyboard
authority, or execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

from app.desktop.contracts import (
    DesktopContextObservation,
    DIAGNOSTICS as DESKTOP_DIAGNOSTICS,
    MAX_TEXT,
)
from app.ui_observation.focus_contracts import (
    FOCUS_STATUS_AVAILABLE,
    FOCUS_STATUS_UNAVAILABLE,
    FocusedUIObservation,
)


MAX_FOCUS_BINDING_AGE_SECONDS = 60.0
MAX_FOCUS_BINDING_GAP_SECONDS = 5.0


REJECTION_CODES = frozenset({
    "clock_unavailable",
    "invalid_focus_metadata",
    "invalid_desktop_metadata",
    "desktop_context_unavailable",
    "focused_ui_unavailable",
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
})


def _timestamp(value):
    if type(value) not in (
        int,
        float,
    ):
        return False

    try:
        return (
            math.isfinite(value)
            and value >= 0
        )
    except OverflowError:
        return False


def _identifier(value):
    return (
        type(value) is str
        and len(value) == 32
        and all(
            character in "0123456789abcdef"
            for character in value
        )
    )


def _bundle(value):
    return (
        type(value) is str
        and 0 < len(value) <= MAX_TEXT
        and bool(value.strip())
    )


def _policy(
    max_age_seconds,
    max_capture_gap_seconds,
):
    return (
        _timestamp(
            max_age_seconds
        )
        and 0.05
        <= max_age_seconds
        <= MAX_FOCUS_BINDING_AGE_SECONDS
        and _timestamp(
            max_capture_gap_seconds
        )
        and 0
        < max_capture_gap_seconds
        <= min(
            MAX_FOCUS_BINDING_GAP_SECONDS,
            max_age_seconds,
        )
    )


def _desktop_source_integrity(
    status,
    diagnostics,
):
    if (
        type(status) is not str
        or status not in (
            "available",
            "partial",
        )
    ):
        raise ValueError(
            "Unavailable desktop evidence cannot be linked."
        )

    if (
        type(diagnostics) is not tuple
        or any(
            type(code) is not str
            or code not in DESKTOP_DIAGNOSTICS
            for code in diagnostics
        )
        or len(set(diagnostics))
        != len(diagnostics)
        or bool(diagnostics)
        != (
            status == "partial"
        )
    ):
        raise ValueError(
            "Desktop diagnostics must preserve source integrity."
        )


def _focus_source_integrity(
    status,
    diagnostics,
):
    if (
        status != FOCUS_STATUS_AVAILABLE
        or diagnostics != ()
    ):
        raise ValueError(
            "Only exact available focus evidence may be linked."
        )


def _match_diagnostics(
    before_status,
    after_status,
):
    if "partial" in (
        before_status,
        after_status,
    ):
        return (
            "desktop_context_partial",
        )

    return ()


@dataclass(frozen=True)
class DesktopFocusBinding:
    """Immutable historical provenance for one exact focus observation."""

    focus_observation_id: str

    desktop_before_id: str
    desktop_after_id: str

    application_pid: int

    application_bundle_id: str = field(
        repr=False
    )

    desktop_before_captured_at: float = 0.0
    focus_captured_at: float = 0.0
    desktop_after_captured_at: float = 0.0

    bound_at_monotonic: float = 0.0
    expires_at_monotonic: float = 0.0

    desktop_before_status: str = "available"
    desktop_after_status: str = "available"
    focus_status: str = FOCUS_STATUS_AVAILABLE

    desktop_before_diagnostics: tuple[str, ...] = ()
    desktop_after_diagnostics: tuple[str, ...] = ()
    focus_diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        ids = (
            self.focus_observation_id,
            self.desktop_before_id,
            self.desktop_after_id,
        )

        if not all(
            _identifier(value)
            for value in ids
        ):
            raise ValueError(
                "Focus binding IDs must be canonical observation IDs."
            )

        if len(set(ids)) != 3:
            raise ValueError(
                "Focus and desktop source observations must be distinct."
            )

        if (
            type(self.application_pid) is not int
            or self.application_pid <= 0
        ):
            raise ValueError(
                "Invalid application PID."
            )

        if not _bundle(
            self.application_bundle_id
        ):
            raise ValueError(
                "Complete application identity is required."
            )

        times = (
            self.desktop_before_captured_at,
            self.focus_captured_at,
            self.desktop_after_captured_at,
            self.bound_at_monotonic,
            self.expires_at_monotonic,
        )

        if not all(
            _timestamp(value)
            for value in times
        ):
            raise ValueError(
                "Focus binding times must be finite and nonnegative."
            )

        (
            before,
            focus,
            after,
            bound,
            expiry,
        ) = times

        if not (
            before
            <= focus
            <= after
            <= bound
            < expiry
            and before < after
        ):
            raise ValueError(
                "Focus binding capture order or expiry is invalid."
            )

        if (
            after - before
            > MAX_FOCUS_BINDING_GAP_SECONDS
            or expiry - before
            > MAX_FOCUS_BINDING_AGE_SECONDS
        ):
            raise ValueError(
                "Focus binding interval exceeds its hard bounds."
            )

        _desktop_source_integrity(
            self.desktop_before_status,
            self.desktop_before_diagnostics,
        )

        _desktop_source_integrity(
            self.desktop_after_status,
            self.desktop_after_diagnostics,
        )

        _focus_source_integrity(
            self.focus_status,
            self.focus_diagnostics,
        )

    def is_fresh(
        self,
        now,
    ):
        """Check recorded lifetime only; never recollect or grant authority."""

        return (
            _timestamp(now)
            and self.bound_at_monotonic
            <= now
            < self.expires_at_monotonic
        )


@dataclass(frozen=True)
class DesktopFocusBindingResult:
    binding: DesktopFocusBinding | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            type(self.diagnostics) is not tuple
            or any(
                type(code) is not str
                for code in self.diagnostics
            )
            or len(set(self.diagnostics))
            != len(self.diagnostics)
        ):
            raise ValueError(
                "Focus binding diagnostics must be immutable and unique."
            )

        if self.binding is None:
            if (
                len(self.diagnostics) != 1
                or self.diagnostics[0]
                not in REJECTION_CODES
            ):
                raise ValueError(
                    "Failed focus binding requires one structured rejection code."
                )

            return

        if type(self.binding) is not DesktopFocusBinding:
            raise ValueError(
                "Invalid desktop-focus binding evidence."
            )

        if any(
            code not in MATCH_DIAGNOSTICS
            for code in self.diagnostics
        ):
            raise ValueError(
                "Successful focus binding diagnostics may "
                "describe desktop partiality only."
            )

        expected = _match_diagnostics(
            self.binding.desktop_before_status,
            self.binding.desktop_after_status,
        )

        if self.diagnostics != expected:
            raise ValueError(
                "Focus binding diagnostics must preserve source integrity."
            )

    @property
    def linked(self):
        return (
            self.binding is not None
        )


def bind_desktop_to_focus(
    focus_observation,
    desktop_before,
    desktop_after,
    *,
    clock=time.monotonic,
    max_age_seconds=5.0,
    max_capture_gap_seconds=3.0,
):
    """Bind one focus observation to exact bracketing desktop evidence.

    No collection, store access, native API, target resolution, model call,
    permission check, text authorization, keyboard action, or execution occurs.

    Application display names and focused-element metadata do not establish
    application identity; only native PID plus exact bundle ID do.
    """

    if not _policy(
        max_age_seconds,
        max_capture_gap_seconds,
    ):
        raise ValueError(
            "Invalid desktop-focus binding age or capture-gap policy."
        )

    if not callable(clock):
        raise TypeError(
            "clock must be callable."
        )

    def reject(code):
        return DesktopFocusBindingResult(
            diagnostics=(
                code,
            )
        )

    try:
        now = clock()
    except Exception:
        return reject(
            "clock_unavailable"
        )

    if not _timestamp(now):
        return reject(
            "clock_unavailable"
        )

    if type(focus_observation) is not FocusedUIObservation:
        return reject(
            "invalid_focus_metadata"
        )

    if (
        type(desktop_before) is not DesktopContextObservation
        or type(desktop_after) is not DesktopContextObservation
    ):
        return reject(
            "invalid_desktop_metadata"
        )

    if (
        desktop_before.status == "unavailable"
        or desktop_after.status == "unavailable"
    ):
        return reject(
            "desktop_context_unavailable"
        )

    if (
        focus_observation.status
        == FOCUS_STATUS_UNAVAILABLE
    ):
        return reject(
            "focused_ui_unavailable"
        )

    if (
        focus_observation.status
        != FOCUS_STATUS_AVAILABLE
    ):
        return reject(
            "invalid_focus_metadata"
        )

    left = (
        desktop_before.active_application
    )

    middle = (
        focus_observation.active_application
    )

    right = (
        desktop_after.active_application
    )

    if (
        left is None
        or middle is None
        or right is None
        or not _bundle(
            left.bundle_id
        )
        or not _bundle(
            middle.bundle_id
        )
        or not _bundle(
            right.bundle_id
        )
    ):
        return reject(
            "application_identity_incomplete"
        )

    if not (
        left.pid
        == middle.pid
        == right.pid
        and left.bundle_id
        == middle.bundle_id
        == right.bundle_id
    ):
        return reject(
            "application_changed"
        )

    ids = (
        focus_observation.observation_id,
        desktop_before.observation_id,
        desktop_after.observation_id,
    )

    if len(set(ids)) != 3:
        return reject(
            "source_observations_not_distinct"
        )

    before = (
        desktop_before.captured_at_monotonic
    )

    focus_captured = (
        focus_observation.captured_at_monotonic
    )

    after = (
        desktop_after.captured_at_monotonic
    )

    if max(
        before,
        focus_captured,
        after,
    ) > now:
        return reject(
            "evidence_from_future"
        )

    if not (
        before
        <= focus_captured
        <= after
        and before < after
    ):
        return reject(
            "capture_order_invalid"
        )

    if (
        after - before
        > max_capture_gap_seconds
    ):
        return reject(
            "capture_gap_exceeded"
        )

    expiry = (
        before
        + max_age_seconds
    )

    if now >= expiry:
        return reject(
            "evidence_expired"
        )

    binding = DesktopFocusBinding(
        focus_observation_id=(
            focus_observation.observation_id
        ),
        desktop_before_id=(
            desktop_before.observation_id
        ),
        desktop_after_id=(
            desktop_after.observation_id
        ),
        application_pid=left.pid,
        application_bundle_id=(
            left.bundle_id
        ),
        desktop_before_captured_at=before,
        focus_captured_at=focus_captured,
        desktop_after_captured_at=after,
        bound_at_monotonic=now,
        expires_at_monotonic=expiry,
        desktop_before_status=(
            desktop_before.status
        ),
        desktop_after_status=(
            desktop_after.status
        ),
        focus_status=(
            focus_observation.status
        ),
        desktop_before_diagnostics=(
            desktop_before.diagnostics
        ),
        desktop_after_diagnostics=(
            desktop_after.diagnostics
        ),
        focus_diagnostics=(
            focus_observation.diagnostics
        ),
    )

    return DesktopFocusBindingResult(
        binding=binding,
        diagnostics=_match_diagnostics(
            desktop_before.status,
            desktop_after.status,
        ),
    )
