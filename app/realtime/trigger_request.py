from __future__ import annotations

"""
KUMA REALTIME-2C — zero-authority caller handoff request.

This module binds one existing ELIGIBLE RealtimeTriggerEligibilityDecision
to the matching RealtimeTriggerProposal and projects a new immutable request
for a future caller-owned handling layer.

It does not wake KUMA, surface UI, invoke callbacks, start workers, mutate
queues, register scheduler jobs, call models/tools, grant permission, or
execute actions.

REQUEST != COMMAND
REQUEST != PERMISSION
REQUEST != WAKE
REQUEST != SURFACE SIDE EFFECT
REQUEST != EXECUTION
REQUEST != VERIFIED COMPLETION
AUTHORITY: NONE
"""

from dataclasses import dataclass
import hashlib
import json

from app.realtime.runtime_trigger import (
    REALTIME_TRIGGER_AUTHORITY_NONE,
    RealtimeTriggerProposal,
)
from app.realtime.trigger_policy import (
    REALTIME_TRIGGER_POLICY_AUTHORITY_NONE,
    RealtimeTriggerEligibilityDecision,
    RealtimeTriggerEligibilityStatus,
)


REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE = "NONE"
MAX_TRIGGER_REQUEST_REASON_CHARS = 160


@dataclass(
    frozen=True,
    slots=True,
)
class RealtimeTriggerRequest:
    """
    Immutable zero-authority handoff request for a future caller-owned layer.

    The request carries only privacy-minimized proposal identity and kind plus
    a bounded structural reason. It contains no callback, UI surface, tool,
    permission, runtime invocation, queue operation, or completion claim.
    """

    request_id: str
    proposal_id: str
    kind: str
    reason: str
    authority: str = (
        REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE
    )

    def __post_init__(
        self,
    ) -> None:
        if not str(
            self.request_id
        ).strip():
            raise ValueError(
                "RealtimeTriggerRequest.request_id cannot be blank."
            )

        if not str(
            self.proposal_id
        ).strip():
            raise ValueError(
                "RealtimeTriggerRequest.proposal_id cannot be blank."
            )

        if not str(
            self.kind
        ).strip():
            raise ValueError(
                "RealtimeTriggerRequest.kind cannot be blank."
            )

        if not str(
            self.reason
        ).strip():
            raise ValueError(
                "RealtimeTriggerRequest.reason cannot be blank."
            )

        if (
            len(
                self.reason
            )
            > MAX_TRIGGER_REQUEST_REASON_CHARS
        ):
            raise ValueError(
                "RealtimeTriggerRequest.reason exceeds the bounded length."
            )

        if (
            self.authority
            != REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE
        ):
            raise ValueError(
                "RealtimeTriggerRequest authority is permanently NONE."
            )


def _clean_reason(
    value: object,
) -> str:
    clean = " ".join(
        str(
            value
        ).split()
    )

    if not clean:
        clean = (
            "eligible realtime trigger awaits "
            "future caller-owned handling"
        )

    return clean[
        :MAX_TRIGGER_REQUEST_REASON_CHARS
    ]


def _request_identity(
    *,
    proposal_id: str,
    kind: str,
    reason: str,
) -> str:
    """
    Deterministic request identity over privacy-minimized handoff metadata only.
    """

    payload = json.dumps(
        {
            "proposal_id": proposal_id,
            "kind": kind,
            "reason": reason,
        },
        sort_keys=True,
        separators=(
            ",",
            ":",
        ),
        ensure_ascii=True,
    ).encode(
        "utf-8"
    )

    return (
        "rtr-"
        + hashlib.sha256(
            payload
        ).hexdigest()
    )


def create_trigger_request(
    proposal: RealtimeTriggerProposal,
    decision: RealtimeTriggerEligibilityDecision,
) -> RealtimeTriggerRequest | None:
    """
    Bind one eligibility decision to its matching proposal.

    INELIGIBLE produces no request. ELIGIBLE produces one immutable
    zero-authority request and then stops. No caller is invoked here.
    """

    if not isinstance(
        proposal,
        RealtimeTriggerProposal,
    ):
        raise TypeError(
            "proposal must be a RealtimeTriggerProposal."
        )

    if not isinstance(
        decision,
        RealtimeTriggerEligibilityDecision,
    ):
        raise TypeError(
            "decision must be a RealtimeTriggerEligibilityDecision."
        )

    if (
        proposal.authority
        != REALTIME_TRIGGER_AUTHORITY_NONE
    ):
        raise ValueError(
            "RealtimeTriggerProposal authority must remain NONE."
        )

    if (
        decision.authority
        != REALTIME_TRIGGER_POLICY_AUTHORITY_NONE
    ):
        raise ValueError(
            "RealtimeTriggerEligibilityDecision authority must remain NONE."
        )

    if (
        decision.proposal_id
        != proposal.proposal_id
    ):
        raise ValueError(
            "eligibility decision must match the proposal identity."
        )

    if (
        decision.status
        == RealtimeTriggerEligibilityStatus.INELIGIBLE
    ):
        return None

    if (
        decision.status
        != RealtimeTriggerEligibilityStatus.ELIGIBLE
    ):
        raise ValueError(
            "unsupported realtime trigger eligibility status."
        )

    proposal_id = str(
        proposal.proposal_id
    ).strip()

    if not proposal_id:
        raise ValueError(
            "proposal.proposal_id cannot be blank."
        )

    kind = str(
        proposal.kind
    ).strip()

    if not kind:
        raise ValueError(
            "proposal.kind cannot be blank."
        )

    reason = _clean_reason(
        decision.reason
    )

    return RealtimeTriggerRequest(
        request_id=_request_identity(
            proposal_id=proposal_id,
            kind=kind,
            reason=reason,
        ),
        proposal_id=proposal_id,
        kind=kind,
        reason=reason,
    )
