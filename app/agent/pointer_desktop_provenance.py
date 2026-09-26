from __future__ import annotations

from dataclasses import dataclass, field
import time

from app.desktop.contracts import (
    DesktopContextObservation,
)


POINTER_PROVENANCE_MAX_AGE_SECONDS = 1.0

POINTER_PROVENANCE_STATUS_AVAILABLE = "available"
POINTER_PROVENANCE_STATUS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class PointerDesktopProvenance:
    desktop_before: DesktopContextObservation
    desktop_after: DesktopContextObservation
    active_application: object
    pointer_x: int
    pointer_y: int
    observed_at_monotonic: float
    expires_at_monotonic: float

    def is_fresh(
        self,
        now,
    ):
        return (
            type(now) in (int, float)
            and self.observed_at_monotonic
            <= now
            <= self.expires_at_monotonic
        )


@dataclass(frozen=True)
class PointerDesktopProvenanceResult:
    status: str
    provenance: PointerDesktopProvenance | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    @property
    def available(self):
        return (
            self.status
            == POINTER_PROVENANCE_STATUS_AVAILABLE
            and self.provenance is not None
        )


def _pointer_xy(
    value,
):
    try:
        if hasattr(value, "x") and hasattr(value, "y"):
            x = value.x
            y = value.y
        else:
            x, y = value

        x = int(x)
        y = int(y)

    except Exception:
        return None

    if x < 0 or y < 0:
        return None

    return (
        x,
        y,
    )


def _inside_active_window(
    observation,
    x,
    y,
):
    windows = getattr(
        observation,
        "windows",
        (),
    )

    for window in windows:
        bounds = getattr(
            window,
            "bounds",
            None,
        )

        if bounds is None:
            continue

        try:
            left = float(bounds.x)
            top = float(bounds.y)
            right = left + float(bounds.width)
            bottom = top + float(bounds.height)
        except Exception:
            continue

        if (
            left <= x < right
            and top <= y < bottom
        ):
            return True

    return False


def _desktop_available(
    observation,
):
    return (
        type(observation)
        is DesktopContextObservation
        and observation.status
        != "unavailable"
        and observation.active_application
        is not None
    )


def collect_pointer_desktop_provenance(
    *,
    desktop_collector=None,
    pointer_reader=None,
    clock=time.monotonic,
):
    def unknown(code):
        return PointerDesktopProvenanceResult(
            status=POINTER_PROVENANCE_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    if desktop_collector is None:
        from app.desktop.runtime import (
            collect_desktop_context,
        )

        desktop_collector = (
            collect_desktop_context
        )

    if pointer_reader is None:
        import pyautogui

        pointer_reader = (
            pyautogui.position
        )

    try:
        before = desktop_collector(
            timeout_seconds=3.0,
            max_windows=32,
        )
    except Exception:
        return unknown(
            "desktop_before_unavailable"
        )

    if not _desktop_available(
        before
    ):
        return unknown(
            "desktop_before_unavailable"
        )

    try:
        raw_pointer = pointer_reader()
        observed_at = clock()
    except Exception:
        return unknown(
            "pointer_unavailable"
        )

    point = _pointer_xy(
        raw_pointer
    )

    if point is None:
        return unknown(
            "pointer_unavailable"
        )

    x, y = point

    try:
        after = desktop_collector(
            timeout_seconds=3.0,
            max_windows=32,
        )
    except Exception:
        return unknown(
            "desktop_after_unavailable"
        )

    if not _desktop_available(
        after
    ):
        return unknown(
            "desktop_after_unavailable"
        )

    if (
        before.active_application
        != after.active_application
    ):
        return unknown(
            "application_identity_changed"
        )

    if not (
        before.captured_at_monotonic
        <= observed_at
        <= after.captured_at_monotonic
    ):
        return unknown(
            "pointer_not_bracketed"
        )

    if not _inside_active_window(
        before,
        x,
        y,
    ):
        return unknown(
            "pointer_outside_active_application"
        )

    if not _inside_active_window(
        after,
        x,
        y,
    ):
        return unknown(
            "pointer_outside_active_application"
        )

    provenance = PointerDesktopProvenance(
        desktop_before=before,
        desktop_after=after,
        active_application=(
            before.active_application
        ),
        pointer_x=x,
        pointer_y=y,
        observed_at_monotonic=(
            observed_at
        ),
        expires_at_monotonic=(
            observed_at
            + POINTER_PROVENANCE_MAX_AGE_SECONDS
        ),
    )

    return PointerDesktopProvenanceResult(
        status=POINTER_PROVENANCE_STATUS_AVAILABLE,
        provenance=provenance,
    )


def revalidate_pointer_desktop_provenance(
    provenance,
    *,
    desktop_collector=None,
    pointer_reader=None,
    clock=time.monotonic,
):
    if (
        type(provenance)
        is not PointerDesktopProvenance
    ):
        return False

    try:
        now = clock()
    except Exception:
        return False

    if not provenance.is_fresh(
        now
    ):
        return False

    result = (
        collect_pointer_desktop_provenance(
            desktop_collector=(
                desktop_collector
            ),
            pointer_reader=(
                pointer_reader
            ),
            clock=clock,
        )
    )

    if not result.available:
        return False

    current = result.provenance

    return (
        current.active_application
        == provenance.active_application
        and current.pointer_x
        == provenance.pointer_x
        and current.pointer_y
        == provenance.pointer_y
    )
