"""B8J runtime producer for one exact structured + visual target carrier.

This stage composes the already-established B8 trust chain for one candidate
``click_vision`` point:

* B8C structured target orchestration,
* B8D structured-target/vision-point binding,
* B8E conjunction with the exact runtime visual verification object, and
* B8F short-lived single-use carrier issuance.

Every production attempt invalidates any previously pending B8F carrier before
new evidence is assembled. A failed attempt therefore cannot fall back to stale
trusted evidence from an earlier candidate.

This module is evidence production only. It performs no UI collection, screen
capture, model verification, permission check, GUI argument authorization,
semantic attestation, ``semantic_target_verified`` assignment, physical action,
or MissionService integration. Those remain later runtime gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time

from app.agent.gui_target_dual_evidence import (
    DUAL_EVIDENCE_STATUS_MATCHED,
    StructuredUIVisualTargetEvidenceResult,
    conjoin_structured_ui_and_visual_target_evidence,
)
from app.agent.gui_target_evidence_carrier import (
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE,
    StructuredUIVisualTargetEvidenceCarrier,
    StructuredUIVisualTargetEvidenceStore,
)
from app.agent.gui_target_orchestration import (
    ORCHESTRATION_STATUS_AVAILABLE,
    StructuredUITargetOrchestrationResult,
    orchestrate_structured_ui_target_evidence,
)
from app.agent.gui_target_point_binding import (
    POINT_BINDING_STATUS_MATCHED,
    StructuredUITargetPointBindingResult,
    bind_structured_ui_target_point,
)
from app.vision.gui_target_verifier import GuiTargetVerificationResult


PRODUCTION_STATUS_ISSUED = "issued"
PRODUCTION_STATUS_UNKNOWN = "unknown"
VALID_PRODUCTION_STATUSES = frozenset({
    PRODUCTION_STATUS_ISSUED,
    PRODUCTION_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "invalid_store",
    "store_reset_failed",
    "orchestration_unavailable",
    "point_binding_unavailable",
    "dual_evidence_unavailable",
    "carrier_issue_failed",
    "invalid_production_contract",
})


@dataclass(frozen=True)
class StructuredUIVisualTargetEvidenceProduction:
    """Exact non-authorizing receipt for one newly issued B8F carrier."""

    orchestration_result: StructuredUITargetOrchestrationResult = field(
        repr=False,
    )
    point_binding_result: StructuredUITargetPointBindingResult = field(
        repr=False,
    )
    dual_evidence_result: StructuredUIVisualTargetEvidenceResult = field(
        repr=False,
    )
    carrier: StructuredUIVisualTargetEvidenceCarrier = field(repr=False)
    visual_verification: GuiTargetVerificationResult = field(repr=False)

    def __post_init__(self):
        if type(self.orchestration_result) is not StructuredUITargetOrchestrationResult:
            raise ValueError("Production requires an exact B8C result.")
        if (
            self.orchestration_result.status != ORCHESTRATION_STATUS_AVAILABLE
            or not self.orchestration_result.available
        ):
            raise ValueError("Production requires available B8C evidence.")

        if type(self.point_binding_result) is not StructuredUITargetPointBindingResult:
            raise ValueError("Production requires an exact B8D result.")
        if (
            self.point_binding_result.status != POINT_BINDING_STATUS_MATCHED
            or not self.point_binding_result.matched
            or self.point_binding_result.binding.orchestration_result
            is not self.orchestration_result
        ):
            raise ValueError("Production requires the exact matched B8C/B8D graph.")

        if type(self.dual_evidence_result) is not StructuredUIVisualTargetEvidenceResult:
            raise ValueError("Production requires an exact B8E result.")
        if (
            self.dual_evidence_result.status != DUAL_EVIDENCE_STATUS_MATCHED
            or not self.dual_evidence_result.matched
            or self.dual_evidence_result.evidence.point_binding_result
            is not self.point_binding_result
            or self.dual_evidence_result.evidence.visual_verification
            is not self.visual_verification
        ):
            raise ValueError("Production requires the exact matched B8D/B8E graph.")

        if type(self.carrier) is not StructuredUIVisualTargetEvidenceCarrier:
            raise ValueError("Production requires an exact B8F carrier.")
        if (
            self.carrier.evidence_result is not self.dual_evidence_result
            or self.carrier.evidence is not self.dual_evidence_result.evidence
            or self.carrier.visual_verification is not self.visual_verification
        ):
            raise ValueError("Production requires the exact B8E/B8F graph.")

    @property
    def screen_observation_id(self):
        return self.carrier.screen_observation_id

    @property
    def ui_observation_id(self):
        return self.carrier.ui_observation_id

    @property
    def vision_point(self):
        return self.carrier.vision_point

    @property
    def native_point(self):
        return self.carrier.native_point

    @property
    def human_goal_sha256(self):
        return self.carrier.human_goal_sha256


@dataclass(frozen=True)
class StructuredUIVisualTargetEvidenceProductionResult:
    status: str
    production: StructuredUIVisualTargetEvidenceProduction | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_PRODUCTION_STATUSES:
            raise ValueError("Invalid target-evidence production status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Production diagnostics must be immutable and unique.")

        if self.status == PRODUCTION_STATUS_ISSUED:
            if type(self.production) is not StructuredUIVisualTargetEvidenceProduction:
                raise ValueError("Issued production requires exact evidence.")
            if self.diagnostics:
                raise ValueError("Issued production has no local diagnostics.")
            return

        if self.production is not None:
            raise ValueError("Unknown production cannot carry trusted evidence.")
        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown production requires one structured diagnostic.")

    @property
    def issued(self):
        return (
            self.status == PRODUCTION_STATUS_ISSUED
            and self.production is not None
        )

    @property
    def carrier(self):
        if not self.issued:
            return None
        return self.production.carrier


def produce_structured_ui_visual_target_evidence(
    intent,
    original_observation,
    original_binding,
    fresh_observation,
    fresh_binding,
    vision_x,
    vision_y,
    visual_verification,
    human_goal,
    *,
    store=STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE,
    clock=time.monotonic,
):
    """Produce and publish one exact B8C -> B8F evidence graph.

    The exact ``visual_verification`` object supplied here must later be passed to
    B8G consumption. Re-running the visual verifier would create a different
    object and correctly fail B8G's identity boundary.
    """

    if type(store) is not StructuredUIVisualTargetEvidenceStore:
        return StructuredUIVisualTargetEvidenceProductionResult(
            status=PRODUCTION_STATUS_UNKNOWN,
            diagnostics=("invalid_store",),
        )
    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(code):
        return StructuredUIVisualTargetEvidenceProductionResult(
            status=PRODUCTION_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    # A new candidate attempt must never inherit a carrier from an earlier one.
    try:
        store.clear()
    except Exception:
        return unknown("store_reset_failed")

    try:
        orchestration_result = orchestrate_structured_ui_target_evidence(
            intent,
            original_observation,
            original_binding,
            fresh_observation,
            fresh_binding,
            clock=clock,
        )
    except Exception:
        return unknown("orchestration_unavailable")

    if (
        type(orchestration_result) is not StructuredUITargetOrchestrationResult
        or orchestration_result.status != ORCHESTRATION_STATUS_AVAILABLE
        or not orchestration_result.available
    ):
        return unknown("orchestration_unavailable")

    try:
        point_binding_result = bind_structured_ui_target_point(
            orchestration_result,
            vision_x,
            vision_y,
            clock=clock,
        )
    except Exception:
        return unknown("point_binding_unavailable")

    if (
        type(point_binding_result) is not StructuredUITargetPointBindingResult
        or point_binding_result.status != POINT_BINDING_STATUS_MATCHED
        or not point_binding_result.matched
    ):
        return unknown("point_binding_unavailable")

    try:
        dual_evidence_result = (
            conjoin_structured_ui_and_visual_target_evidence(
                point_binding_result,
                visual_verification,
                human_goal,
                clock=clock,
            )
        )
    except Exception:
        return unknown("dual_evidence_unavailable")

    if (
        type(dual_evidence_result) is not StructuredUIVisualTargetEvidenceResult
        or dual_evidence_result.status != DUAL_EVIDENCE_STATUS_MATCHED
        or not dual_evidence_result.matched
        or dual_evidence_result.evidence.visual_verification
        is not visual_verification
    ):
        return unknown("dual_evidence_unavailable")

    try:
        carrier = store.issue(
            dual_evidence_result,
            clock=clock,
        )
    except Exception:
        # Even a partially failing/custom store implementation must not leave
        # candidate evidence pending after a failed production attempt.
        try:
            store.clear()
        except Exception:
            pass
        return unknown("carrier_issue_failed")

    try:
        production = StructuredUIVisualTargetEvidenceProduction(
            orchestration_result=orchestration_result,
            point_binding_result=point_binding_result,
            dual_evidence_result=dual_evidence_result,
            carrier=carrier,
            visual_verification=visual_verification,
        )
    except Exception:
        # A malformed final graph must not leave an issued carrier usable.
        try:
            store.clear()
        except Exception:
            pass
        return unknown("invalid_production_contract")

    return StructuredUIVisualTargetEvidenceProductionResult(
        status=PRODUCTION_STATUS_ISSUED,
        production=production,
    )
