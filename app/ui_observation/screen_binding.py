"""Pure provenance join between desktop-bound structured UI and trusted screen evidence.

A StructuredUIScreenBinding proves only that an exact structured UI observation
and an exact trusted screen observation were each bound to the same two trusted
desktop source observations. It does not prove pixel-to-element correspondence,
element stability, user intent, permission, or action authority.
"""

from dataclasses import dataclass
import math
import time

from app.desktop.provenance import ScreenDesktopProvenance
from app.ui_observation.desktop_binding import DesktopUIBinding


REJECTION_CODES = frozenset({
    "clock_unavailable",
    "invalid_ui_binding",
    "invalid_screen_provenance",
    "desktop_source_mismatch",
    "application_identity_mismatch",
    "desktop_metadata_mismatch",
    "evidence_id_collision",
    "source_binding_from_future",
    "source_binding_expired",
})

MATCH_DIAGNOSTICS = frozenset({
    "desktop_context_partial",
    "structured_ui_partial",
})


def _timestamp(value):
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


def _match_diagnostics(binding):
    diagnostics = []
    if "partial" in (
        binding.ui_binding.desktop_before_status,
        binding.ui_binding.desktop_after_status,
    ):
        diagnostics.append("desktop_context_partial")
    if binding.ui_binding.ui_status == "partial":
        diagnostics.append("structured_ui_partial")
    return tuple(diagnostics)


def _screen_binding(screen_provenance):
    return screen_provenance.binding


def _shared_desktop_ids(ui_binding, screen_provenance):
    screen = _screen_binding(screen_provenance)
    return (
        ui_binding.desktop_before_id == screen.desktop_before_id
        and ui_binding.desktop_after_id == screen.desktop_after_id
    )


def _shared_application(ui_binding, screen_provenance):
    screen = _screen_binding(screen_provenance)
    return (
        ui_binding.application_pid == screen.application_pid
        and ui_binding.application_bundle_id == screen.application_bundle_id
    )


def _shared_desktop_metadata(ui_binding, screen_provenance):
    screen = _screen_binding(screen_provenance)
    return (
        ui_binding.desktop_before_captured_at
        == screen.desktop_before_captured_at
        and ui_binding.desktop_after_captured_at
        == screen.desktop_after_captured_at
        and ui_binding.desktop_before_status
        == screen.desktop_before_status
        and ui_binding.desktop_after_status
        == screen.desktop_after_status
        and ui_binding.desktop_before_diagnostics
        == screen.desktop_before_diagnostics
        and ui_binding.desktop_after_diagnostics
        == screen.desktop_after_diagnostics
    )


@dataclass(frozen=True)
class StructuredUIScreenBinding:
    """Immutable join over one exact trusted desktop bracket."""

    ui_binding: DesktopUIBinding
    screen_provenance: ScreenDesktopProvenance
    linked_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.ui_binding) is not DesktopUIBinding:
            raise ValueError("A trusted desktop-UI binding is required.")
        if type(self.screen_provenance) is not ScreenDesktopProvenance:
            raise ValueError("Trusted screen-desktop provenance is required.")

        if not _shared_desktop_ids(self.ui_binding, self.screen_provenance):
            raise ValueError("Source bindings do not share exact desktop observation IDs.")
        if not _shared_application(self.ui_binding, self.screen_provenance):
            raise ValueError("Source bindings do not share exact application identity.")
        if not _shared_desktop_metadata(self.ui_binding, self.screen_provenance):
            raise ValueError("Source bindings do not preserve identical desktop metadata.")

        screen = _screen_binding(self.screen_provenance)
        ids = (
            self.ui_binding.ui_observation_id,
            screen.screen_observation_id,
            self.ui_binding.desktop_before_id,
            self.ui_binding.desktop_after_id,
        )
        if not all(_identifier(value) for value in ids) or len(set(ids)) != 4:
            raise ValueError("Joined evidence IDs must be canonical and distinct.")

        times = (
            self.ui_binding.desktop_before_captured_at,
            self.ui_binding.ui_captured_at,
            screen.screen_captured_at,
            self.ui_binding.desktop_after_captured_at,
            self.ui_binding.bound_at_monotonic,
            screen.bound_at_monotonic,
            self.linked_at_monotonic,
            self.expires_at_monotonic,
        )
        if not all(_timestamp(value) for value in times):
            raise ValueError("Joined evidence times must be finite and nonnegative.")

        before, ui, screen_captured, after, ui_bound, screen_bound, linked, expiry = times
        if not (
            before <= ui <= after
            and before <= screen_captured <= after
            and max(ui_bound, screen_bound) <= linked < expiry
        ):
            raise ValueError("Joined evidence timing is invalid.")

        expected_expiry = min(
            self.ui_binding.expires_at_monotonic,
            screen.expires_at_monotonic,
        )
        if expiry != expected_expiry:
            raise ValueError("Joined evidence expiry must equal the earliest source expiry.")

    @property
    def ui_observation_id(self):
        return self.ui_binding.ui_observation_id

    @property
    def screen_observation_id(self):
        return self.screen_provenance.binding.screen_observation_id

    @property
    def desktop_before_id(self):
        return self.ui_binding.desktop_before_id

    @property
    def desktop_after_id(self):
        return self.ui_binding.desktop_after_id

    @property
    def application_pid(self):
        return self.ui_binding.application_pid

    @property
    def application_bundle_id(self):
        return self.ui_binding.application_bundle_id

    def is_fresh(self, now):
        """Check recorded lifetime only; never recollect or grant authority."""
        return (
            _timestamp(now)
            and self.linked_at_monotonic <= now < self.expires_at_monotonic
        )


@dataclass(frozen=True)
class StructuredUIScreenBindingResult:
    binding: StructuredUIScreenBinding | None = None
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
                raise ValueError("Failed join requires one structured rejection code.")
            return

        if type(self.binding) is not StructuredUIScreenBinding:
            raise ValueError("Invalid structured-UI/screen binding evidence.")
        if any(code not in MATCH_DIAGNOSTICS for code in self.diagnostics):
            raise ValueError("Successful diagnostics may describe partial evidence only.")
        if self.diagnostics != _match_diagnostics(self.binding):
            raise ValueError("Diagnostics must preserve source integrity.")

    @property
    def linked(self):
        return self.binding is not None


def bind_structured_ui_to_screen(
    ui_binding,
    screen_provenance,
    *,
    clock=time.monotonic,
):
    """Join trusted UI binding with exact screen-desktop provenance.

    No collection, screen capture, model, store, native API, AX action,
    permission check, target resolution, or execution occurs here.
    """

    if not callable(clock):
        raise TypeError("clock must be callable.")

    def reject(code):
        return StructuredUIScreenBindingResult(diagnostics=(code,))

    try:
        now = clock()
    except Exception:
        return reject("clock_unavailable")
    if not _timestamp(now):
        return reject("clock_unavailable")

    if type(ui_binding) is not DesktopUIBinding:
        return reject("invalid_ui_binding")
    if type(screen_provenance) is not ScreenDesktopProvenance:
        return reject("invalid_screen_provenance")

    if not _shared_desktop_ids(ui_binding, screen_provenance):
        return reject("desktop_source_mismatch")
    if not _shared_application(ui_binding, screen_provenance):
        return reject("application_identity_mismatch")
    if not _shared_desktop_metadata(ui_binding, screen_provenance):
        return reject("desktop_metadata_mismatch")

    screen = _screen_binding(screen_provenance)
    ids = (
        ui_binding.ui_observation_id,
        screen.screen_observation_id,
        ui_binding.desktop_before_id,
        ui_binding.desktop_after_id,
    )
    if len(set(ids)) != 4:
        return reject("evidence_id_collision")

    latest_bound = max(
        ui_binding.bound_at_monotonic,
        screen.bound_at_monotonic,
    )
    if now < latest_bound:
        return reject("source_binding_from_future")

    expiry = min(
        ui_binding.expires_at_monotonic,
        screen.expires_at_monotonic,
    )
    if now >= expiry:
        return reject("source_binding_expired")

    binding = StructuredUIScreenBinding(
        ui_binding=ui_binding,
        screen_provenance=screen_provenance,
        linked_at_monotonic=now,
        expires_at_monotonic=expiry,
    )
    return StructuredUIScreenBindingResult(
        binding=binding,
        diagnostics=_match_diagnostics(binding),
    )
