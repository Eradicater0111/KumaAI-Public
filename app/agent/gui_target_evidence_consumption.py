"""B8G exact consumption boundary for one trusted B8F target carrier.

This stage consumes one pending B8F carrier for the exact normalized human goal,
trusted screen observation, and vision point, then requires that the runtime's
GuiTargetVerificationResult is the exact same object already bound into B8E/B8F.

The B8F claim happens before visual-result validation so every consumption attempt
retains B8F's single-use fail-closed semantics. A matched consumption is evidence
only. It grants no permission, argument authority, target attestation,
``semantic_target_verified`` state, or execution capability.

Nothing here wires the carrier into MissionService. A later integration stage must
preserve the existing desktop-context, permission, semantic-attestation,
target-region pixel-continuity, and physical execution gates.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib

from app.agent.gui_target_evidence_carrier import (
    STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE,
    StructuredUIVisualTargetEvidenceCarrier,
    StructuredUIVisualTargetEvidenceStore,
)
from app.vision.gui_target_verifier import (
    GuiTargetVerificationResult,
    TARGET_STATUS_SATISFIED,
)


CONSUMPTION_STATUS_MATCHED = "matched"
CONSUMPTION_STATUS_UNKNOWN = "unknown"
VALID_CONSUMPTION_STATUSES = frozenset({
    CONSUMPTION_STATUS_MATCHED,
    CONSUMPTION_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "invalid_store",
    "carrier_unavailable",
    "invalid_visual_verification",
    "visual_verification_unavailable",
    "visual_identity_mismatch",
    "screen_observation_mismatch",
    "candidate_point_mismatch",
    "human_goal_mismatch",
    "invalid_consumption_contract",
})


def _trusted_goal(value):
    if type(value) is not str:
        return None
    value = value.strip()
    return value if value else None


def _goal_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_hex(value):
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _valid_satisfied_visual_result(result):
    return (
        type(result) is GuiTargetVerificationResult
        and result.status == TARGET_STATUS_SATISFIED
        and type(result.summary) is str
        and bool(result.summary.strip())
        and type(result.evidence) is str
        and bool(result.evidence.strip())
        and type(result.observation_id) is str
        and bool(result.observation_id)
        and type(result.x) is int
        and type(result.y) is int
        and result.x >= 0
        and result.y >= 0
        and _sha256_hex(result.goal_sha256)
        and _sha256_hex(result.image_sha256)
        and _sha256_hex(result.target_region_sha256)
    )


@dataclass(frozen=True)
class StructuredUIVisualTargetEvidenceConsumption:
    """Exact non-authorizing receipt for one successfully claimed B8F carrier."""

    carrier: StructuredUIVisualTargetEvidenceCarrier = field(repr=False)
    visual_verification: GuiTargetVerificationResult = field(repr=False)
    human_goal_sha256: str

    def __post_init__(self):
        if type(self.carrier) is not StructuredUIVisualTargetEvidenceCarrier:
            raise ValueError("Consumption requires an exact B8F carrier.")
        if not _valid_satisfied_visual_result(self.visual_verification):
            raise ValueError("Consumption requires valid satisfied visual evidence.")
        if self.carrier.visual_verification is not self.visual_verification:
            raise ValueError("Consumption requires the exact B8F visual object.")
        if not _sha256_hex(self.human_goal_sha256):
            raise ValueError("Consumption requires a trusted human-goal digest.")
        if self.human_goal_sha256 != self.carrier.human_goal_sha256:
            raise ValueError("Consumption belongs to a different human goal.")
        if self.visual_verification.goal_sha256 != self.human_goal_sha256:
            raise ValueError("Visual evidence belongs to a different human goal.")
        if self.visual_verification.observation_id != self.carrier.screen_observation_id:
            raise ValueError("Visual evidence belongs to a different screen observation.")
        if (self.visual_verification.x, self.visual_verification.y) != self.carrier.vision_point:
            raise ValueError("Visual evidence belongs to a different candidate point.")

    @property
    def evidence(self):
        return self.carrier.evidence

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
    def target_region_sha256(self):
        return self.visual_verification.target_region_sha256

    def is_current(self, now):
        return self.carrier.is_current(now)


@dataclass(frozen=True)
class StructuredUIVisualTargetEvidenceConsumptionResult:
    status: str
    consumption: StructuredUIVisualTargetEvidenceConsumption | None = field(
        default=None,
        repr=False,
    )
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_CONSUMPTION_STATUSES:
            raise ValueError("Invalid dual target-evidence consumption status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Consumption diagnostics must be immutable and unique.")

        if self.status == CONSUMPTION_STATUS_MATCHED:
            if type(self.consumption) is not StructuredUIVisualTargetEvidenceConsumption:
                raise ValueError("Matched consumption requires exact evidence.")
            if self.diagnostics:
                raise ValueError("Matched consumption has no local diagnostics.")
            return

        if self.consumption is not None:
            raise ValueError("Unknown consumption cannot carry trusted evidence.")
        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown consumption requires one structured diagnostic.")

    @property
    def matched(self):
        return (
            self.status == CONSUMPTION_STATUS_MATCHED
            and self.consumption is not None
        )


def consume_structured_ui_visual_target_evidence(
    visual_verification,
    *,
    human_goal,
    observation_id,
    x,
    y,
    store=STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE,
    clock=None,
):
    """Consume exact B8F evidence and bind it to the runtime visual object.

    B8F performs the first gate and consumes its pending carrier on every claim
    attempt. Only a successful exact claim is then compared to the runtime visual
    result by object identity. No authority state is created here.
    """

    if type(store) is not StructuredUIVisualTargetEvidenceStore:
        return StructuredUIVisualTargetEvidenceConsumptionResult(
            status=CONSUMPTION_STATUS_UNKNOWN,
            diagnostics=("invalid_store",),
        )

    if clock is None:
        import time
        clock = time.monotonic
    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(code):
        return StructuredUIVisualTargetEvidenceConsumptionResult(
            status=CONSUMPTION_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    # Claim first. B8F therefore consumes the pending carrier even when the
    # supplied runtime visual object below is malformed, stale, or substituted.
    try:
        carrier = store.claim(
            human_goal=human_goal,
            observation_id=observation_id,
            x=x,
            y=y,
            clock=clock,
        )
    except Exception:
        return unknown("carrier_unavailable")

    if type(visual_verification) is not GuiTargetVerificationResult:
        return unknown("invalid_visual_verification")
    if visual_verification.status != TARGET_STATUS_SATISFIED:
        return unknown("visual_verification_unavailable")
    if not _valid_satisfied_visual_result(visual_verification):
        return unknown("invalid_visual_verification")

    # Value equality is insufficient. The verifier result used by the runtime
    # must be the exact object already conjoined into B8E and carried by B8F.
    if carrier.visual_verification is not visual_verification:
        return unknown("visual_identity_mismatch")

    trusted_goal = _trusted_goal(human_goal)
    if trusted_goal is None:
        return unknown("human_goal_mismatch")
    goal_sha256 = _goal_digest(trusted_goal)
    if (
        goal_sha256 != carrier.human_goal_sha256
        or visual_verification.goal_sha256 != goal_sha256
    ):
        return unknown("human_goal_mismatch")
    if visual_verification.observation_id != carrier.screen_observation_id:
        return unknown("screen_observation_mismatch")
    if (visual_verification.x, visual_verification.y) != carrier.vision_point:
        return unknown("candidate_point_mismatch")

    try:
        consumption = StructuredUIVisualTargetEvidenceConsumption(
            carrier=carrier,
            visual_verification=visual_verification,
            human_goal_sha256=goal_sha256,
        )
    except Exception:
        return unknown("invalid_consumption_contract")

    return StructuredUIVisualTargetEvidenceConsumptionResult(
        status=CONSUMPTION_STATUS_MATCHED,
        consumption=consumption,
    )
