"""Fresh semantic continuity checks for previously resolved structured UI targets.

B7 never treats an AX path, rectangle, or stale coordinate as stable identity. It
re-resolves the original normalized selector against a strictly newer exact UI +
screen provenance bundle, then compares conservative semantic identity evidence.

A successful revalidation is evidence only. It performs no collection, model
call, store lookup, coordinate conversion, permission check, target attestation,
AX action, or GUI execution and it grants no authority.
"""

from dataclasses import dataclass
import math
import time

from app.ui_observation.contracts import StructuredUIObservation, UIElementObservation
from app.ui_observation.screen_binding import StructuredUIScreenBinding
from app.ui_observation.target_resolution import (
    ResolvedStructuredUITarget,
    StructuredUITargetResolutionResult,
    TARGET_STATUS_AMBIGUOUS,
    TARGET_STATUS_RESOLVED,
    TARGET_STATUS_UNKNOWN,
    resolve_structured_ui_target,
)


CONTINUITY_STATUS_MATCHED = "matched"
CONTINUITY_STATUS_MISMATCH = "mismatch"
CONTINUITY_STATUS_UNKNOWN = "unknown"
VALID_CONTINUITY_STATUSES = frozenset({
    CONTINUITY_STATUS_MATCHED,
    CONTINUITY_STATUS_MISMATCH,
    CONTINUITY_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "clock_unavailable",
    "invalid_original_target",
    "invalid_fresh_observation",
    "invalid_fresh_binding",
    "original_target_from_future",
    "original_target_expired",
    "fresh_binding_from_future",
    "fresh_binding_expired",
    "fresh_evidence_not_newer",
    "fresh_evidence_reused",
    "fresh_target_unknown",
    "identity_evidence_insufficient",
})

MISMATCH_CODES = frozenset({
    "application_identity_changed",
    "fresh_target_ambiguous",
    "semantic_identity_changed",
})

SOURCE_DIAGNOSTICS = frozenset({
    "desktop_context_partial",
    "structured_ui_partial",
})


def _timestamp(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _normalized_optional_text(value):
    if type(value) is not str or not value.strip():
        return None
    return value.strip().casefold()


def _fresh_ids(binding):
    return (
        binding.ui_observation_id,
        binding.screen_observation_id,
        binding.desktop_before_id,
        binding.desktop_after_id,
    )


def _has_identity_anchor(element):
    """Role/subrole alone are too generic for cross-snapshot continuity."""
    return (
        _normalized_optional_text(element.title) is not None
        or _normalized_optional_text(element.description) is not None
    )


def _semantic_identity_continuity(original, fresh):
    """Return True, False, or None for conservative semantic continuity.

    Snapshot-local path and native geometry are deliberately ignored. Mutable UI
    state such as enabled/focused/selected is also not identity. Missing fresh
    evidence for an originally known semantic field is unknown, while a known
    contradiction is a mismatch.
    """

    if (
        type(original) is not UIElementObservation
        or type(fresh) is not UIElementObservation
    ):
        return None

    if not _has_identity_anchor(original):
        return None

    comparisons = []

    if original.role is not None:
        if fresh.role is None:
            comparisons.append(None)
        else:
            comparisons.append(fresh.role == original.role)

    if original.subrole is not None:
        if fresh.subrole is None:
            comparisons.append(None)
        else:
            comparisons.append(fresh.subrole == original.subrole)

    original_title = _normalized_optional_text(original.title)
    if original_title is not None:
        fresh_title = _normalized_optional_text(fresh.title)
        comparisons.append(
            None if fresh_title is None else fresh_title == original_title
        )

    original_description = _normalized_optional_text(original.description)
    if original_description is not None:
        fresh_description = _normalized_optional_text(fresh.description)
        comparisons.append(
            None
            if fresh_description is None
            else fresh_description == original_description
        )

    if any(value is False for value in comparisons):
        return False
    if any(value is None for value in comparisons):
        return None
    return True


@dataclass(frozen=True)
class RevalidatedStructuredUITarget:
    """Fresh evidence that a prior semantic target was re-established.

    This does not claim native AX object identity. It proves only conservative
    semantic continuity inside the same exact application process, using a
    strictly newer trusted observation/provenance bundle.
    """

    original: ResolvedStructuredUITarget
    fresh_resolution: ResolvedStructuredUITarget
    revalidated_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.original) is not ResolvedStructuredUITarget:
            raise ValueError("A previously resolved structured UI target is required.")
        if type(self.fresh_resolution) is not ResolvedStructuredUITarget:
            raise ValueError("A fresh resolved structured UI target is required.")
        if not all(_timestamp(value) for value in (
            self.revalidated_at_monotonic,
            self.expires_at_monotonic,
        )):
            raise ValueError("Revalidation times must be finite and nonnegative.")

        fresh = self.fresh_resolution
        original = self.original

        if self.revalidated_at_monotonic != fresh.resolved_at_monotonic:
            raise ValueError("Revalidation must be issued with the fresh resolution.")
        if not (
            original.resolved_at_monotonic
            <= self.revalidated_at_monotonic
            < original.expires_at_monotonic
        ):
            raise ValueError("Original target was not fresh when revalidated.")
        if self.expires_at_monotonic != fresh.expires_at_monotonic:
            raise ValueError("Revalidated evidence cannot outlive fresh source evidence.")
        if not (
            self.revalidated_at_monotonic
            < self.expires_at_monotonic
        ):
            raise ValueError("Fresh revalidation evidence is already expired.")

        if fresh.selector is not original.selector:
            raise ValueError("Revalidation must reuse the exact original selector.")

        if (
            original.application_pid != fresh.application_pid
            or original.application_bundle_id != fresh.application_bundle_id
        ):
            raise ValueError("Application identity changed across revalidation.")

        if not (
            fresh.observation.captured_at_monotonic
            > original.observation.captured_at_monotonic
            and fresh.binding.linked_at_monotonic
            > original.binding.linked_at_monotonic
            and fresh.resolved_at_monotonic
            > original.resolved_at_monotonic
        ):
            raise ValueError("Fresh target evidence must be strictly newer.")

        if set(_fresh_ids(original.binding)) & set(_fresh_ids(fresh.binding)):
            raise ValueError("Fresh revalidation cannot reuse prior evidence IDs.")

        continuity = _semantic_identity_continuity(
            original.element,
            fresh.element,
        )
        if continuity is not True:
            raise ValueError("Semantic target continuity is not established.")

    @property
    def observation(self):
        return self.fresh_resolution.observation

    @property
    def binding(self):
        return self.fresh_resolution.binding

    @property
    def selector(self):
        return self.original.selector

    @property
    def element(self):
        return self.fresh_resolution.element

    @property
    def ui_observation_id(self):
        return self.fresh_resolution.ui_observation_id

    @property
    def screen_observation_id(self):
        return self.fresh_resolution.screen_observation_id

    @property
    def application_pid(self):
        return self.fresh_resolution.application_pid

    @property
    def application_bundle_id(self):
        return self.fresh_resolution.application_bundle_id

    @property
    def path(self):
        return self.fresh_resolution.path

    def is_fresh(self, now):
        return (
            _timestamp(now)
            and self.revalidated_at_monotonic <= now < self.expires_at_monotonic
        )


@dataclass(frozen=True)
class StructuredUITargetRevalidationResult:
    status: str
    revalidation: RevalidatedStructuredUITarget | None = None
    fresh_resolution: StructuredUITargetResolutionResult | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_CONTINUITY_STATUSES:
            raise ValueError("Invalid target revalidation status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Revalidation diagnostics must be immutable and unique.")
        if (
            self.fresh_resolution is not None
            and type(self.fresh_resolution) is not StructuredUITargetResolutionResult
        ):
            raise ValueError("Fresh resolution evidence is invalid.")

        if self.status == CONTINUITY_STATUS_MATCHED:
            if type(self.revalidation) is not RevalidatedStructuredUITarget:
                raise ValueError("Revalidated status requires exact continuity evidence.")
            if (
                self.fresh_resolution is None
                or not self.fresh_resolution.resolved
                or self.fresh_resolution.resolution
                is not self.revalidation.fresh_resolution
            ):
                raise ValueError("Revalidated status requires its exact fresh resolution.")
            if any(code not in SOURCE_DIAGNOSTICS for code in self.diagnostics):
                raise ValueError("Successful revalidation may preserve source partiality only.")
            if self.diagnostics != self.fresh_resolution.diagnostics:
                raise ValueError("Successful diagnostics must preserve fresh source integrity.")
            return

        if self.revalidation is not None:
            raise ValueError("Unsuccessful revalidation cannot contain continuity evidence.")

        if self.status == CONTINUITY_STATUS_MISMATCH:
            if len(self.diagnostics) != 1 or self.diagnostics[0] not in MISMATCH_CODES:
                raise ValueError("Mismatch requires one structured mismatch diagnostic.")
            if self.fresh_resolution is None:
                raise ValueError("Mismatch requires fresh target evidence.")
            code = self.diagnostics[0]
            if (
                code == "fresh_target_ambiguous"
                and self.fresh_resolution.status != TARGET_STATUS_AMBIGUOUS
            ):
                raise ValueError("Ambiguity mismatch requires ambiguous fresh evidence.")
            if (
                code in {"application_identity_changed", "semantic_identity_changed"}
                and self.fresh_resolution.status != TARGET_STATUS_RESOLVED
            ):
                raise ValueError("Identity mismatch requires resolved fresh evidence.")
            return

        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown revalidation requires one structured diagnostic.")
        code = self.diagnostics[0]
        if (
            code == "fresh_target_unknown"
            and (
                self.fresh_resolution is None
                or self.fresh_resolution.status != TARGET_STATUS_UNKNOWN
            )
        ):
            raise ValueError("Fresh-target unknown requires unknown fresh resolution evidence.")
        if (
            code == "identity_evidence_insufficient"
            and (
                self.fresh_resolution is None
                or self.fresh_resolution.status != TARGET_STATUS_RESOLVED
            )
        ):
            raise ValueError("Identity uncertainty requires resolved fresh target evidence.")

    @property
    def revalidated(self):
        return (
            self.status == CONTINUITY_STATUS_MATCHED
            and self.revalidation is not None
        )


def revalidate_structured_ui_target(
    original,
    fresh_observation,
    fresh_binding,
    *,
    clock=time.monotonic,
):
    """Revalidate one prior resolved target against strictly newer evidence.

    The original selector is re-used exactly; callers cannot broaden or replace
    it during revalidation. ``revalidated`` means conservative semantic
    continuity, not stable AX object identity and not permission to act.
    """

    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(code, fresh_resolution=None):
        return StructuredUITargetRevalidationResult(
            status=CONTINUITY_STATUS_UNKNOWN,
            fresh_resolution=fresh_resolution,
            diagnostics=(code,),
        )

    def mismatch(code, fresh_resolution):
        return StructuredUITargetRevalidationResult(
            status=CONTINUITY_STATUS_MISMATCH,
            fresh_resolution=fresh_resolution,
            diagnostics=(code,),
        )

    try:
        now = clock()
    except Exception:
        return unknown("clock_unavailable")
    if not _timestamp(now):
        return unknown("clock_unavailable")

    if type(original) is not ResolvedStructuredUITarget:
        return unknown("invalid_original_target")
    if type(fresh_observation) is not StructuredUIObservation:
        return unknown("invalid_fresh_observation")
    if type(fresh_binding) is not StructuredUIScreenBinding:
        return unknown("invalid_fresh_binding")

    if now < original.resolved_at_monotonic:
        return unknown("original_target_from_future")
    if now >= original.expires_at_monotonic:
        return unknown("original_target_expired")
    if now < fresh_binding.linked_at_monotonic:
        return unknown("fresh_binding_from_future")
    if now >= fresh_binding.expires_at_monotonic:
        return unknown("fresh_binding_expired")

    if (
        fresh_observation.captured_at_monotonic
        <= original.observation.captured_at_monotonic
        or fresh_binding.linked_at_monotonic
        <= original.binding.linked_at_monotonic
    ):
        return unknown("fresh_evidence_not_newer")

    if set(_fresh_ids(original.binding)) & set(_fresh_ids(fresh_binding)):
        return unknown("fresh_evidence_reused")

    fresh_result = resolve_structured_ui_target(
        fresh_observation,
        fresh_binding,
        original.selector,
        clock=lambda: now,
    )

    if fresh_result.status == TARGET_STATUS_UNKNOWN:
        return unknown("fresh_target_unknown", fresh_result)

    if fresh_result.status == TARGET_STATUS_AMBIGUOUS:
        return mismatch("fresh_target_ambiguous", fresh_result)

    if (
        fresh_result.status != TARGET_STATUS_RESOLVED
        or not fresh_result.resolved
    ):
        return unknown("fresh_target_unknown", fresh_result)

    fresh = fresh_result.resolution

    if (
        fresh.application_pid != original.application_pid
        or fresh.application_bundle_id != original.application_bundle_id
    ):
        return mismatch("application_identity_changed", fresh_result)

    continuity = _semantic_identity_continuity(
        original.element,
        fresh.element,
    )
    if continuity is False:
        return mismatch("semantic_identity_changed", fresh_result)
    if continuity is None:
        return unknown("identity_evidence_insufficient", fresh_result)

    revalidation = RevalidatedStructuredUITarget(
        original=original,
        fresh_resolution=fresh,
        revalidated_at_monotonic=now,
        expires_at_monotonic=fresh.expires_at_monotonic,
    )

    return StructuredUITargetRevalidationResult(
        status=CONTINUITY_STATUS_MATCHED,
        revalidation=revalidation,
        fresh_resolution=fresh_result,
        diagnostics=fresh_result.diagnostics,
    )
