"""Trusted envelope for planner intent plus B6/B7 structured-UI evidence.

B8B binds one planner-facing semantic target intent to the *exact selector object*
that was used by B6 and preserved by B7, then carries the matched B7 result as
read-only evidence. It never converts AX geometry to click coordinates and never
grants permission, attestation, semantic-target verification, or execution
authority.

Strings and IDs may describe evidence, but they cannot construct this envelope.
There is deliberately no ``from_dict`` or serialization-based reconstruction API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import time

from app.agent.gui_target_intent import StructuredUITargetIntent
from app.ui_observation.target_resolution import StructuredUITargetSelector
from app.ui_observation.target_revalidation import (
    CONTINUITY_STATUS_MATCHED,
    RevalidatedStructuredUITarget,
    StructuredUITargetRevalidationResult,
)


EVIDENCE_STATUS_AVAILABLE = "available"
EVIDENCE_STATUS_UNKNOWN = "unknown"
VALID_EVIDENCE_STATUSES = frozenset({
    EVIDENCE_STATUS_AVAILABLE,
    EVIDENCE_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "clock_unavailable",
    "invalid_intent",
    "invalid_selector",
    "invalid_revalidation",
    "revalidation_not_matched",
    "intent_selector_mismatch",
    "selector_identity_mismatch",
    "evidence_from_future",
    "evidence_expired",
    "invalid_evidence_contract",
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


def _intent_matches_selector(intent, selector):
    if (
        type(intent) is not StructuredUITargetIntent
        or type(selector) is not StructuredUITargetSelector
    ):
        return False
    return selector == intent.to_selector()


@dataclass(frozen=True)
class StructuredUITargetEvidence:
    """Read-only semantic evidence for one exact planner target requirement.

    ``selector`` is intentionally stored as an object reference. B8C must create
    it once from ``intent`` and pass that exact object through B6/B7. Equal-value
    selector substitution is rejected even when every string happens to match.

    This evidence is not a visual-target attestation and has no action authority.
    """

    intent: StructuredUITargetIntent = field(repr=False)
    selector: StructuredUITargetSelector = field(repr=False)
    revalidation_result: StructuredUITargetRevalidationResult = field(repr=False)
    assembled_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.intent) is not StructuredUITargetIntent:
            raise ValueError("Structured UI target evidence requires target intent.")
        if type(self.selector) is not StructuredUITargetSelector:
            raise ValueError("Structured UI target evidence requires an exact selector.")
        if type(self.revalidation_result) is not StructuredUITargetRevalidationResult:
            raise ValueError("Structured UI target evidence requires B7 result evidence.")

        result = self.revalidation_result
        if (
            result.status != CONTINUITY_STATUS_MATCHED
            or not result.revalidated
            or type(result.revalidation) is not RevalidatedStructuredUITarget
        ):
            raise ValueError("Only matched B7 continuity may become target evidence.")

        revalidation = result.revalidation

        if not _intent_matches_selector(self.intent, self.selector):
            raise ValueError("Target intent does not match the exact selector requirements.")

        if revalidation.selector is not self.selector:
            raise ValueError("B7 did not preserve the exact trusted selector object.")

        if (
            result.fresh_resolution is None
            or not result.fresh_resolution.resolved
            or result.fresh_resolution.resolution is not revalidation.fresh_resolution
        ):
            raise ValueError("B7 result does not carry its exact fresh resolution graph.")

        if not all(_timestamp(value) for value in (
            self.assembled_at_monotonic,
            self.expires_at_monotonic,
        )):
            raise ValueError("Structured UI target evidence times are invalid.")

        if not (
            revalidation.revalidated_at_monotonic
            <= self.assembled_at_monotonic
            < self.expires_at_monotonic
        ):
            raise ValueError("Structured UI target evidence timing is invalid.")

        if self.expires_at_monotonic != revalidation.expires_at_monotonic:
            raise ValueError("Target evidence cannot change the B7 lifetime.")

        if (
            type(result.diagnostics) is not tuple
            or any(code not in SOURCE_DIAGNOSTICS for code in result.diagnostics)
        ):
            raise ValueError("Target evidence must preserve B7 source diagnostics.")

    @property
    def revalidation(self):
        return self.revalidation_result.revalidation

    @property
    def original_ui_observation_id(self):
        return self.revalidation.original.ui_observation_id

    @property
    def ui_observation_id(self):
        return self.revalidation.ui_observation_id

    @property
    def screen_observation_id(self):
        return self.revalidation.screen_observation_id

    @property
    def application_pid(self):
        return self.revalidation.application_pid

    @property
    def application_bundle_id(self):
        return self.revalidation.application_bundle_id

    @property
    def snapshot_path(self):
        """Snapshot-local AX path for audit only; never stable identity."""
        return self.revalidation.path

    @property
    def ax_geometry(self):
        """Raw B5 AX geometry evidence; never a click-coordinate mapping."""
        element = self.revalidation.element
        return (
            element.position_x,
            element.position_y,
            element.width,
            element.height,
        )

    @property
    def source_diagnostics(self):
        return self.revalidation_result.diagnostics

    def is_fresh(self, now):
        return (
            _timestamp(now)
            and self.assembled_at_monotonic <= now < self.expires_at_monotonic
        )


@dataclass(frozen=True)
class StructuredUITargetEvidenceResult:
    status: str
    evidence: StructuredUITargetEvidence | None = None
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_EVIDENCE_STATUSES:
            raise ValueError("Invalid structured UI target evidence status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Target evidence diagnostics must be immutable and unique.")

        if self.status == EVIDENCE_STATUS_AVAILABLE:
            if type(self.evidence) is not StructuredUITargetEvidence:
                raise ValueError("Available status requires exact target evidence.")
            if self.diagnostics != self.evidence.source_diagnostics:
                raise ValueError("Available diagnostics must preserve B7 source integrity.")
            return

        if self.evidence is not None:
            raise ValueError("Unknown status cannot carry trusted target evidence.")
        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown status requires one structured diagnostic.")

    @property
    def available(self):
        return self.status == EVIDENCE_STATUS_AVAILABLE and self.evidence is not None


def assemble_structured_ui_target_evidence(
    intent,
    selector,
    revalidation_result,
    *,
    clock=time.monotonic,
):
    """Bind planner requirements to exact matched B7 evidence, fail closed.

    The caller must supply the same selector object originally created from the
    planner intent and used for B6. B7 already requires that same selector object
    to survive into the fresh resolution. No IDs, paths, geometry, or status
    strings supplied by a model can substitute for this object graph.
    """

    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(code):
        return StructuredUITargetEvidenceResult(
            status=EVIDENCE_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    try:
        now = clock()
    except Exception:
        return unknown("clock_unavailable")

    if not _timestamp(now):
        return unknown("clock_unavailable")

    if type(intent) is not StructuredUITargetIntent:
        return unknown("invalid_intent")
    if type(selector) is not StructuredUITargetSelector:
        return unknown("invalid_selector")
    if type(revalidation_result) is not StructuredUITargetRevalidationResult:
        return unknown("invalid_revalidation")

    if (
        revalidation_result.status != CONTINUITY_STATUS_MATCHED
        or not revalidation_result.revalidated
        or type(revalidation_result.revalidation) is not RevalidatedStructuredUITarget
    ):
        return unknown("revalidation_not_matched")

    if not _intent_matches_selector(intent, selector):
        return unknown("intent_selector_mismatch")

    revalidation = revalidation_result.revalidation

    if revalidation.selector is not selector:
        return unknown("selector_identity_mismatch")

    if now < revalidation.revalidated_at_monotonic:
        return unknown("evidence_from_future")
    if now >= revalidation.expires_at_monotonic:
        return unknown("evidence_expired")

    try:
        evidence = StructuredUITargetEvidence(
            intent=intent,
            selector=selector,
            revalidation_result=revalidation_result,
            assembled_at_monotonic=now,
            expires_at_monotonic=revalidation.expires_at_monotonic,
        )
    except Exception:
        return unknown("invalid_evidence_contract")

    return StructuredUITargetEvidenceResult(
        status=EVIDENCE_STATUS_AVAILABLE,
        evidence=evidence,
        diagnostics=revalidation_result.diagnostics,
    )
