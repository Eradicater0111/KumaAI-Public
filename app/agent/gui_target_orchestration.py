"""Pure B8C orchestration for exact structured-UI target evidence.

B8C composes the existing trust-preserving stages:

* B8A planner-facing semantic target intent,
* B6 exact structured-UI target resolution,
* B7 fresh semantic target continuity revalidation, and
* B8B trusted target evidence assembly.

The authoritative selector is constructed once from the intent, passed to B6,
preserved by B7, and supplied unchanged to B8B. B8B may independently construct
an equal-value selector only to check intent/selector value integrity; that
comparison object never replaces the authoritative selector in the trusted
object graph.

This module performs no UI collection, store lookup, coordinate conversion,
permission check, human confirmation, target attestation,
``semantic_target_verified`` assignment, AX action, tool execution, or GUI
execution. Successful orchestration is evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from app.agent.gui_target_evidence import (
    EVIDENCE_STATUS_AVAILABLE,
    StructuredUITargetEvidenceResult,
    assemble_structured_ui_target_evidence,
)
from app.agent.gui_target_intent import StructuredUITargetIntent
from app.ui_observation.target_resolution import (
    StructuredUITargetResolutionResult,
    StructuredUITargetSelector,
    TARGET_STATUS_RESOLVED,
    resolve_structured_ui_target,
)
from app.ui_observation.target_revalidation import (
    CONTINUITY_STATUS_MATCHED,
    StructuredUITargetRevalidationResult,
    revalidate_structured_ui_target,
)


ORCHESTRATION_STATUS_AVAILABLE = "available"
ORCHESTRATION_STATUS_UNKNOWN = "unknown"
VALID_ORCHESTRATION_STATUSES = frozenset({
    ORCHESTRATION_STATUS_AVAILABLE,
    ORCHESTRATION_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "invalid_intent",
    "selector_construction_failed",
    "initial_resolution_unavailable",
    "continuity_unavailable",
    "evidence_unavailable",
    "invalid_orchestration_contract",
})


@dataclass(frozen=True)
class StructuredUITargetOrchestrationResult:
    """Read-only B8A -> B6 -> B7 -> B8B evidence composition result."""

    status: str
    intent: StructuredUITargetIntent | None = field(default=None, repr=False)
    selector: StructuredUITargetSelector | None = field(default=None, repr=False)
    resolution_result: StructuredUITargetResolutionResult | None = field(
        default=None,
        repr=False,
    )
    revalidation_result: StructuredUITargetRevalidationResult | None = field(
        default=None,
        repr=False,
    )
    evidence_result: StructuredUITargetEvidenceResult | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if (
            type(self.status) is not str
            or self.status not in VALID_ORCHESTRATION_STATUSES
        ):
            raise ValueError("Invalid structured UI target orchestration status.")

        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError(
                "Structured UI target orchestration diagnostics must be "
                "immutable and unique."
            )

        optional_contracts = (
            (self.intent, StructuredUITargetIntent, "intent"),
            (self.selector, StructuredUITargetSelector, "selector"),
            (
                self.resolution_result,
                StructuredUITargetResolutionResult,
                "B6 result",
            ),
            (
                self.revalidation_result,
                StructuredUITargetRevalidationResult,
                "B7 result",
            ),
            (
                self.evidence_result,
                StructuredUITargetEvidenceResult,
                "B8B result",
            ),
        )
        for value, expected, name in optional_contracts:
            if value is not None and type(value) is not expected:
                raise ValueError(
                    f"Structured UI target orchestration has invalid {name}."
                )

        if self.status == ORCHESTRATION_STATUS_AVAILABLE:
            if (
                self.intent is None
                or self.selector is None
                or self.resolution_result is None
                or self.revalidation_result is None
                or self.evidence_result is None
            ):
                raise ValueError(
                    "Available orchestration requires the complete exact "
                    "evidence graph."
                )

            resolution = self.resolution_result
            revalidation = self.revalidation_result
            evidence_result = self.evidence_result

            if (
                resolution.status != TARGET_STATUS_RESOLVED
                or not resolution.resolved
                or resolution.resolution.selector is not self.selector
            ):
                raise ValueError(
                    "Available orchestration requires B6 to preserve the "
                    "exact selector."
                )

            if (
                revalidation.status != CONTINUITY_STATUS_MATCHED
                or not revalidation.revalidated
                or revalidation.revalidation.original
                is not resolution.resolution
                or revalidation.revalidation.selector is not self.selector
            ):
                raise ValueError(
                    "Available orchestration requires B7 to preserve the "
                    "exact B6 object graph."
                )

            if (
                evidence_result.status != EVIDENCE_STATUS_AVAILABLE
                or not evidence_result.available
                or evidence_result.evidence.intent is not self.intent
                or evidence_result.evidence.selector is not self.selector
                or evidence_result.evidence.revalidation_result
                is not self.revalidation_result
            ):
                raise ValueError(
                    "Available orchestration requires exact B8B evidence "
                    "identity."
                )

            if self.diagnostics != evidence_result.diagnostics:
                raise ValueError(
                    "Available orchestration must preserve B8B source "
                    "diagnostics."
                )
            return

        if (
            len(self.diagnostics) != 1
            or self.diagnostics[0] not in UNKNOWN_CODES
        ):
            raise ValueError(
                "Unknown orchestration requires one structured diagnostic."
            )

        if (
            self.evidence_result is not None
            and self.evidence_result.available
        ):
            raise ValueError(
                "Unknown orchestration cannot carry available B8B evidence."
            )

    @property
    def available(self):
        return (
            self.status == ORCHESTRATION_STATUS_AVAILABLE
            and self.evidence_result is not None
            and self.evidence_result.available
        )

    @property
    def evidence(self):
        if not self.available:
            return None
        return self.evidence_result.evidence


def orchestrate_structured_ui_target_evidence(
    intent,
    original_observation,
    original_binding,
    fresh_observation,
    fresh_binding,
    *,
    clock=time.monotonic,
):
    """Compose B8A/B6/B7/B8B while preserving one authoritative selector.

    The supplied clock is passed through to every stage instead of sampled once.
    B6, B7, and B8B retain their own freshness semantics, and B7 requires the
    fresh resolution time to be strictly newer than the original B6 resolution.
    """

    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(
        code,
        *,
        trusted_intent=None,
        selector=None,
        resolution_result=None,
        revalidation_result=None,
        evidence_result=None,
    ):
        return StructuredUITargetOrchestrationResult(
            status=ORCHESTRATION_STATUS_UNKNOWN,
            intent=trusted_intent,
            selector=selector,
            resolution_result=resolution_result,
            revalidation_result=revalidation_result,
            evidence_result=evidence_result,
            diagnostics=(code,),
        )

    if type(intent) is not StructuredUITargetIntent:
        return unknown("invalid_intent")

    try:
        selector = intent.to_selector()
    except Exception:
        return unknown(
            "selector_construction_failed",
            trusted_intent=intent,
        )

    try:
        resolution_result = resolve_structured_ui_target(
            original_observation,
            original_binding,
            selector,
            clock=clock,
        )
    except Exception:
        return unknown(
            "initial_resolution_unavailable",
            trusted_intent=intent,
            selector=selector,
        )

    if (
        resolution_result.status != TARGET_STATUS_RESOLVED
        or not resolution_result.resolved
        or resolution_result.resolution.selector is not selector
    ):
        return unknown(
            "initial_resolution_unavailable",
            trusted_intent=intent,
            selector=selector,
            resolution_result=resolution_result,
        )

    try:
        revalidation_result = revalidate_structured_ui_target(
            resolution_result.resolution,
            fresh_observation,
            fresh_binding,
            clock=clock,
        )
    except Exception:
        return unknown(
            "continuity_unavailable",
            trusted_intent=intent,
            selector=selector,
            resolution_result=resolution_result,
        )

    if (
        revalidation_result.status != CONTINUITY_STATUS_MATCHED
        or not revalidation_result.revalidated
        or revalidation_result.revalidation.original
        is not resolution_result.resolution
        or revalidation_result.revalidation.selector is not selector
    ):
        return unknown(
            "continuity_unavailable",
            trusted_intent=intent,
            selector=selector,
            resolution_result=resolution_result,
            revalidation_result=revalidation_result,
        )

    try:
        evidence_result = assemble_structured_ui_target_evidence(
            intent,
            selector,
            revalidation_result,
            clock=clock,
        )
    except Exception:
        return unknown(
            "evidence_unavailable",
            trusted_intent=intent,
            selector=selector,
            resolution_result=resolution_result,
            revalidation_result=revalidation_result,
        )

    if (
        evidence_result.status != EVIDENCE_STATUS_AVAILABLE
        or not evidence_result.available
    ):
        return unknown(
            "evidence_unavailable",
            trusted_intent=intent,
            selector=selector,
            resolution_result=resolution_result,
            revalidation_result=revalidation_result,
            evidence_result=evidence_result,
        )

    try:
        return StructuredUITargetOrchestrationResult(
            status=ORCHESTRATION_STATUS_AVAILABLE,
            intent=intent,
            selector=selector,
            resolution_result=resolution_result,
            revalidation_result=revalidation_result,
            evidence_result=evidence_result,
            diagnostics=evidence_result.diagnostics,
        )
    except Exception:
        return unknown(
            "invalid_orchestration_contract",
            trusted_intent=intent,
            selector=selector,
            resolution_result=resolution_result,
            revalidation_result=revalidation_result,
        )
