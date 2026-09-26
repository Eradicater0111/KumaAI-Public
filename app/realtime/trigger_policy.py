from __future__ import annotations

"""
KUMA REALTIME-2B — zero-authority trigger eligibility policy.

This module evaluates an already-existing RealtimeTriggerProposal against
explicit caller-supplied eligibility criteria. It does not choose those
criteria, wake KUMA, surface UI, drain signals, call tools, grant permission,
or execute actions.

ELIGIBILITY != COMMAND
ELIGIBILITY != PERMISSION
ELIGIBILITY != WAKE
ELIGIBILITY != EXECUTION
ELIGIBILITY != VERIFIED COMPLETION
AUTHORITY: NONE
"""

from dataclasses import dataclass
from enum import Enum
import math

from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
)
from app.realtime.runtime_trigger import (
    REALTIME_TRIGGER_AUTHORITY_NONE,
    RealtimeTriggerProposal,
)


REALTIME_TRIGGER_POLICY_AUTHORITY_NONE = "NONE"


class RealtimeTriggerEligibilityStatus(
    str,
    Enum,
):
    INELIGIBLE = "ineligible"
    ELIGIBLE = "eligible"


_LEVEL_RANK = {
    RealtimeRelevanceLevel.IGNORE: 0,
    RealtimeRelevanceLevel.LOW: 1,
    RealtimeRelevanceLevel.MEDIUM: 2,
    RealtimeRelevanceLevel.HIGH: 3,
}


@dataclass(
    frozen=True,
    slots=True,
)
class RealtimeTriggerEligibilityDecision:
    """
    Zero-authority result of evaluating one trigger proposal.

    The decision records only proposal identity, eligibility status, and a
    bounded structural reason. It grants no permission and carries no
    executable action, callback, tool, or completion claim.
    """

    proposal_id: str
    status: RealtimeTriggerEligibilityStatus
    reason: str
    authority: str = (
        REALTIME_TRIGGER_POLICY_AUTHORITY_NONE
    )

    def __post_init__(
        self,
    ) -> None:
        if not str(
            self.proposal_id
        ).strip():
            raise ValueError(
                "proposal_id cannot be blank."
            )

        if not isinstance(
            self.status,
            RealtimeTriggerEligibilityStatus,
        ):
            raise TypeError(
                "status must be RealtimeTriggerEligibilityStatus."
            )

        if not str(
            self.reason
        ).strip():
            raise ValueError(
                "reason cannot be blank."
            )

        if (
            self.authority
            != REALTIME_TRIGGER_POLICY_AUTHORITY_NONE
        ):
            raise ValueError(
                "RealtimeTriggerEligibilityDecision authority is permanently NONE."
            )

    @property
    def eligible(
        self,
    ) -> bool:
        return (
            self.status
            == RealtimeTriggerEligibilityStatus.ELIGIBLE
        )


def _validate_threshold_score(
    value: float,
) -> float:
    score = float(
        value
    )

    if (
        not math.isfinite(
            score
        )
        or not 0.0 <= score <= 1.0
    ):
        raise ValueError(
            "minimum_score must be finite and between 0.0 and 1.0."
        )

    return score


def evaluate_trigger_eligibility(
    proposal: RealtimeTriggerProposal,
    *,
    minimum_level: RealtimeRelevanceLevel,
    minimum_score: float,
) -> RealtimeTriggerEligibilityDecision:
    """
    Evaluate one zero-authority proposal against explicit caller criteria.

    The caller supplies both thresholds. REALTIME-2B does not own wake policy
    and therefore does not hide or manufacture threshold values.

    This function is pure with respect to KUMA runtime state.
    """

    if not isinstance(
        proposal,
        RealtimeTriggerProposal,
    ):
        raise TypeError(
            "proposal must be a RealtimeTriggerProposal."
        )

    if (
        proposal.authority
        != REALTIME_TRIGGER_AUTHORITY_NONE
    ):
        raise ValueError(
            "RealtimeTriggerProposal authority must remain NONE."
        )

    if not isinstance(
        minimum_level,
        RealtimeRelevanceLevel,
    ):
        raise TypeError(
            "minimum_level must be RealtimeRelevanceLevel."
        )

    if (
        minimum_level
        == RealtimeRelevanceLevel.IGNORE
    ):
        raise ValueError(
            "minimum_level cannot be IGNORE for runtime-trigger eligibility."
        )

    threshold = (
        _validate_threshold_score(
            minimum_score
        )
    )

    level_ok = (
        _LEVEL_RANK[
            proposal.level
        ]
        >= _LEVEL_RANK[
            minimum_level
        ]
    )

    score_ok = (
        float(
            proposal.score
        )
        >= threshold
    )

    if (
        level_ok
        and score_ok
    ):
        return (
            RealtimeTriggerEligibilityDecision(
                proposal_id=proposal.proposal_id,
                status=(
                    RealtimeTriggerEligibilityStatus.ELIGIBLE
                ),
                reason=(
                    "proposal satisfies the explicit "
                    "caller-supplied relevance thresholds"
                ),
            )
        )

    failures = []

    if not level_ok:
        failures.append(
            "relevance level below explicit minimum"
        )

    if not score_ok:
        failures.append(
            "relevance score below explicit minimum"
        )

    return (
        RealtimeTriggerEligibilityDecision(
            proposal_id=proposal.proposal_id,
            status=(
                RealtimeTriggerEligibilityStatus.INELIGIBLE
            ),
            reason="; ".join(
                failures
            ),
        )
    )
