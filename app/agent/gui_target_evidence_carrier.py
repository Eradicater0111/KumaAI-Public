"""B8F short-lived in-memory carrier for exact B8E target evidence.

This stage stores at most one exact matched StructuredUIVisualTargetEvidenceResult
in process memory and permits a single claim bound to the same normalized human
goal, trusted screen observation ID, and vision point.

The carrier is evidence transport only. It grants no permission, action authority,
target attestation, ``semantic_target_verified`` state, or execution capability.
It is deliberately not serializable and is not planner/model metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
import threading
import time

from app.agent.gui_target_dual_evidence import (
    DUAL_EVIDENCE_STATUS_MATCHED,
    StructuredUIVisualTargetEvidence,
    StructuredUIVisualTargetEvidenceResult,
)


def _timestamp(value):
    return (
        type(value) in (int, float)
        and math.isfinite(value)
        and value >= 0
    )


def _trusted_goal(value):
    if type(value) is not str:
        return None
    value = value.strip()
    return value if value else None


def _goal_digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class StructuredUIVisualTargetEvidenceCarrier:
    """One exact short-lived in-memory reference to matched B8E evidence."""

    evidence_result: StructuredUIVisualTargetEvidenceResult = field(repr=False)
    evidence: StructuredUIVisualTargetEvidence = field(repr=False)
    issued_at_monotonic: float
    expires_at_monotonic: float

    def __post_init__(self):
        if type(self.evidence_result) is not StructuredUIVisualTargetEvidenceResult:
            raise ValueError("Carrier requires an exact B8E result.")
        if (
            self.evidence_result.status != DUAL_EVIDENCE_STATUS_MATCHED
            or not self.evidence_result.matched
            or self.evidence_result.evidence is not self.evidence
        ):
            raise ValueError("Carrier requires the exact matched B8E evidence graph.")
        if type(self.evidence) is not StructuredUIVisualTargetEvidence:
            raise ValueError("Carrier requires exact B8E evidence.")
        if not all(_timestamp(value) for value in (
            self.issued_at_monotonic,
            self.expires_at_monotonic,
        )):
            raise ValueError("Carrier times are invalid.")
        if not self.evidence.is_current(self.issued_at_monotonic):
            raise ValueError("Carrier requires current B8E evidence.")
        if not (
            self.issued_at_monotonic
            < self.expires_at_monotonic
            <= self.evidence.expires_at_monotonic
        ):
            raise ValueError("Carrier cannot outlive B8E evidence.")

    @property
    def human_goal_sha256(self):
        return self.evidence.human_goal_sha256

    @property
    def screen_observation_id(self):
        return self.evidence.screen_observation_id

    @property
    def ui_observation_id(self):
        return self.evidence.ui_observation_id

    @property
    def vision_point(self):
        return self.evidence.vision_point

    @property
    def native_point(self):
        return self.evidence.native_point

    @property
    def visual_verification(self):
        return self.evidence.visual_verification

    def is_current(self, now):
        return (
            _timestamp(now)
            and self.issued_at_monotonic <= now < self.expires_at_monotonic
            and self.evidence.is_current(now)
        )


class StructuredUIVisualTargetEvidenceStore:
    """Hold at most one exact B8E carrier; every claim attempt consumes it."""

    def __init__(self, *, max_age_seconds: float = 5.0):
        if (
            type(max_age_seconds) not in (int, float)
            or not math.isfinite(max_age_seconds)
            or max_age_seconds <= 0
        ):
            raise ValueError("max_age_seconds must be finite and positive.")

        self.max_age_seconds = float(max_age_seconds)
        self._active: StructuredUIVisualTargetEvidenceCarrier | None = None
        self._lock = threading.Lock()

    def issue(
        self,
        result: StructuredUIVisualTargetEvidenceResult,
        *,
        clock=time.monotonic,
    ) -> StructuredUIVisualTargetEvidenceCarrier:
        if not callable(clock):
            raise TypeError("clock must be callable.")

        try:
            now = clock()
        except Exception:
            raise ValueError("Carrier clock is unavailable.") from None
        if not _timestamp(now):
            raise ValueError("Carrier clock is unavailable.")

        if type(result) is not StructuredUIVisualTargetEvidenceResult:
            raise ValueError("Only an exact B8E result may be carried.")
        if (
            result.status != DUAL_EVIDENCE_STATUS_MATCHED
            or not result.matched
            or type(result.evidence) is not StructuredUIVisualTargetEvidence
        ):
            raise ValueError("Only matched B8E evidence may be carried.")

        evidence = result.evidence
        if not evidence.is_current(now):
            raise ValueError("B8E evidence is not current.")

        expires_at = min(
            evidence.expires_at_monotonic,
            now + self.max_age_seconds,
        )

        carrier = StructuredUIVisualTargetEvidenceCarrier(
            evidence_result=result,
            evidence=evidence,
            issued_at_monotonic=now,
            expires_at_monotonic=expires_at,
        )

        with self._lock:
            self._active = carrier

        return carrier

    def claim(
        self,
        *,
        human_goal,
        observation_id,
        x,
        y,
        clock=time.monotonic,
    ) -> StructuredUIVisualTargetEvidenceCarrier:
        if not callable(clock):
            raise TypeError("clock must be callable.")

        # Every claim attempt consumes or invalidates the pending carrier.
        with self._lock:
            carrier = self._active
            self._active = None

        if carrier is None:
            raise ValueError("No dual target-evidence carrier is active.")

        try:
            now = clock()
        except Exception:
            raise ValueError("Carrier clock is unavailable.") from None
        if not _timestamp(now) or not carrier.is_current(now):
            raise ValueError("Dual target-evidence carrier expired.")

        trusted_goal = _trusted_goal(human_goal)
        if trusted_goal is None:
            raise ValueError("A trusted human goal is required.")
        if type(observation_id) is not str or not observation_id:
            raise ValueError("A trusted screen observation ID is required.")
        if type(x) is not int or type(y) is not int or x < 0 or y < 0:
            raise ValueError("Candidate coordinates must be non-negative integers.")

        if _goal_digest(trusted_goal) != carrier.human_goal_sha256:
            raise ValueError("Carrier belongs to a different human goal.")
        if observation_id != carrier.screen_observation_id:
            raise ValueError("Carrier belongs to a different screen observation.")
        if (x, y) != carrier.vision_point:
            raise ValueError("Carrier belongs to a different candidate point.")

        return carrier

    def clear(self) -> None:
        with self._lock:
            self._active = None


STRUCTURED_UI_VISUAL_TARGET_EVIDENCE_STORE = (
    StructuredUIVisualTargetEvidenceStore()
)
