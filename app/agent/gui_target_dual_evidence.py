"""B8E conjunction of structured target-point and visual target evidence.

This stage joins one exact matched B8D point-binding result with one satisfied
GuiTargetVerificationResult for the same trusted screen observation, vision
point, and original human mission goal.

The visual result carries no monotonic timestamp, so this object deliberately
does not claim visual freshness. B8D source lifetime remains bounded here, while
the existing target-region pixel continuity gate remains the final visual
freshness predicate before physical execution.

A matched conjunction is evidence only. It grants no permission, action
authority, target attestation, ``semantic_target_verified`` state, or execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import time

from app.agent.gui_target_point_binding import (
    POINT_BINDING_STATUS_MATCHED,
    StructuredUITargetPointBinding,
    StructuredUITargetPointBindingResult,
)
from app.vision.gui_target_verifier import (
    GuiTargetVerificationResult,
    TARGET_STATUS_SATISFIED,
)


DUAL_EVIDENCE_STATUS_MATCHED = "matched"
DUAL_EVIDENCE_STATUS_UNKNOWN = "unknown"
VALID_DUAL_EVIDENCE_STATUSES = frozenset({
    DUAL_EVIDENCE_STATUS_MATCHED,
    DUAL_EVIDENCE_STATUS_UNKNOWN,
})

UNKNOWN_CODES = frozenset({
    "clock_unavailable",
    "invalid_human_goal",
    "invalid_point_binding",
    "point_binding_unavailable",
    "point_binding_not_current",
    "invalid_visual_verification",
    "visual_verification_unavailable",
    "screen_observation_mismatch",
    "candidate_point_mismatch",
    "human_goal_mismatch",
    "invalid_conjunction_contract",
})


def _timestamp(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_hex(value):
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _trusted_goal(value):
    if type(value) is not str:
        return None
    value = value.strip()
    return value if value else None


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
class StructuredUIVisualTargetEvidence:
    """Exact non-authorizing conjunction of B8D and visual target evidence."""

    point_binding_result: StructuredUITargetPointBindingResult = field(repr=False)
    point_binding: StructuredUITargetPointBinding = field(repr=False)
    visual_verification: GuiTargetVerificationResult = field(repr=False)
    human_goal_sha256: str
    assembled_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.point_binding_result) is not StructuredUITargetPointBindingResult:
            raise ValueError("Dual evidence requires an exact B8D result.")
        if (
            self.point_binding_result.status != POINT_BINDING_STATUS_MATCHED
            or not self.point_binding_result.matched
            or self.point_binding_result.binding is not self.point_binding
        ):
            raise ValueError("Dual evidence requires the exact matched B8D binding graph.")
        if type(self.point_binding) is not StructuredUITargetPointBinding:
            raise ValueError("Dual evidence requires exact B8D point evidence.")
        if not _valid_satisfied_visual_result(self.visual_verification):
            raise ValueError("Dual evidence requires a valid satisfied visual result.")
        if not _sha256_hex(self.human_goal_sha256):
            raise ValueError("Dual evidence requires the trusted human-goal digest.")
        if not all(_timestamp(value) for value in (
            self.assembled_at_monotonic,
            self.expires_at_monotonic,
        )):
            raise ValueError("Dual-evidence times are invalid.")
        if not (
            self.point_binding.checked_at_monotonic
            <= self.assembled_at_monotonic
            < self.expires_at_monotonic
        ):
            raise ValueError("Dual evidence is outside the B8D source lifetime.")
        if self.expires_at_monotonic != self.point_binding.expires_at_monotonic:
            raise ValueError("Dual evidence cannot extend the B8D lifetime.")

        visual = self.visual_verification
        if visual.observation_id != self.point_binding.screen_observation_id:
            raise ValueError("Visual evidence belongs to a different screen observation.")
        if (visual.x, visual.y) != self.point_binding.vision_point:
            raise ValueError("Visual evidence belongs to a different candidate point.")
        if visual.goal_sha256 != self.human_goal_sha256:
            raise ValueError("Visual evidence belongs to a different human goal.")

    @property
    def screen_observation_id(self):
        return self.point_binding.screen_observation_id

    @property
    def ui_observation_id(self):
        return self.point_binding.ui_observation_id

    @property
    def vision_point(self):
        return self.point_binding.vision_point

    @property
    def native_point(self):
        return self.point_binding.native_point

    @property
    def structured_evidence(self):
        return self.point_binding.evidence

    @property
    def target_region_sha256(self):
        return self.visual_verification.target_region_sha256

    def is_current(self, now):
        """Check only the bounded B8D lifetime; visual freshness is separate."""
        return (
            _timestamp(now)
            and self.assembled_at_monotonic <= now < self.expires_at_monotonic
        )


@dataclass(frozen=True)
class StructuredUIVisualTargetEvidenceResult:
    status: str
    evidence: StructuredUIVisualTargetEvidence | None = field(default=None, repr=False)
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self):
        if type(self.status) is not str or self.status not in VALID_DUAL_EVIDENCE_STATUSES:
            raise ValueError("Invalid dual target-evidence status.")
        if (
            type(self.diagnostics) is not tuple
            or any(type(code) is not str for code in self.diagnostics)
            or len(set(self.diagnostics)) != len(self.diagnostics)
        ):
            raise ValueError("Dual target-evidence diagnostics must be immutable and unique.")

        if self.status == DUAL_EVIDENCE_STATUS_MATCHED:
            if type(self.evidence) is not StructuredUIVisualTargetEvidence:
                raise ValueError("Matched dual evidence requires exact evidence.")
            if self.diagnostics:
                raise ValueError("Matched dual evidence has no local diagnostics.")
            return

        if self.evidence is not None:
            raise ValueError("Unknown dual evidence cannot carry trusted evidence.")
        if len(self.diagnostics) != 1 or self.diagnostics[0] not in UNKNOWN_CODES:
            raise ValueError("Unknown dual evidence requires one structured diagnostic.")

    @property
    def matched(self):
        return (
            self.status == DUAL_EVIDENCE_STATUS_MATCHED
            and self.evidence is not None
        )


def conjoin_structured_ui_and_visual_target_evidence(
    point_binding_result,
    visual_verification,
    human_goal,
    *,
    clock=time.monotonic,
):
    """Conjoin exact B8D and visual evidence for one human-authorized point.

    The caller is responsible for supplying the exact result returned by
    ``safe_verify_gui_target``. This function rechecks its complete satisfied
    evidence contract and exact goal/observation/point correspondence, but the
    visual result type itself has no hidden origin token or timestamp.
    """

    if not callable(clock):
        raise TypeError("clock must be callable.")

    def unknown(code):
        return StructuredUIVisualTargetEvidenceResult(
            status=DUAL_EVIDENCE_STATUS_UNKNOWN,
            diagnostics=(code,),
        )

    try:
        now = clock()
    except Exception:
        return unknown("clock_unavailable")
    if not _timestamp(now):
        return unknown("clock_unavailable")

    trusted_goal = _trusted_goal(human_goal)
    if trusted_goal is None:
        return unknown("invalid_human_goal")

    if type(point_binding_result) is not StructuredUITargetPointBindingResult:
        return unknown("invalid_point_binding")
    if (
        point_binding_result.status != POINT_BINDING_STATUS_MATCHED
        or not point_binding_result.matched
        or type(point_binding_result.binding) is not StructuredUITargetPointBinding
    ):
        return unknown("point_binding_unavailable")

    point_binding = point_binding_result.binding
    if not (
        point_binding.checked_at_monotonic
        <= now
        < point_binding.expires_at_monotonic
    ):
        return unknown("point_binding_not_current")

    if type(visual_verification) is not GuiTargetVerificationResult:
        return unknown("invalid_visual_verification")
    if visual_verification.status != TARGET_STATUS_SATISFIED:
        return unknown("visual_verification_unavailable")
    if not _valid_satisfied_visual_result(visual_verification):
        return unknown("invalid_visual_verification")

    if visual_verification.observation_id != point_binding.screen_observation_id:
        return unknown("screen_observation_mismatch")
    if (visual_verification.x, visual_verification.y) != point_binding.vision_point:
        return unknown("candidate_point_mismatch")

    goal_sha256 = _digest(trusted_goal)
    if visual_verification.goal_sha256 != goal_sha256:
        return unknown("human_goal_mismatch")

    try:
        evidence = StructuredUIVisualTargetEvidence(
            point_binding_result=point_binding_result,
            point_binding=point_binding,
            visual_verification=visual_verification,
            human_goal_sha256=goal_sha256,
            assembled_at_monotonic=now,
            expires_at_monotonic=point_binding.expires_at_monotonic,
        )
    except Exception:
        return unknown("invalid_conjunction_contract")

    return StructuredUIVisualTargetEvidenceResult(
        status=DUAL_EVIDENCE_STATUS_MATCHED,
        evidence=evidence,
    )
