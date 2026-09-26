from __future__ import annotations

"""
KUMA REALTIME-2D — zero-authority trigger-request observation.

This module projects one already-existing RealtimeTriggerRequest into an
immutable observation record for a future caller-owned handling layer.

It does not acknowledge delivery, accept responsibility, notify a user, wake
KUMA, invoke callbacks, start workers, mutate queues, register scheduler jobs,
call models/tools, grant permission, or execute actions.

OBSERVATION != ACKNOWLEDGMENT
OBSERVATION != ACCEPTANCE
OBSERVATION != DELIVERY
OBSERVATION != NOTIFICATION
OBSERVATION != WAKE
OBSERVATION != EXECUTION
OBSERVATION != VERIFIED COMPLETION
AUTHORITY: NONE
"""

from dataclasses import dataclass
from enum import Enum
import hashlib
import json

from app.realtime.trigger_request import (
    REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE,
    RealtimeTriggerRequest,
)


REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE = "NONE"


class RealtimeTriggerObservationStatus(
    str,
    Enum,
):
    OBSERVED = "observed"


@dataclass(
    frozen=True,
    slots=True,
)
class RealtimeTriggerObservation:
    """
    Immutable zero-authority observation of one trigger request.

    OBSERVED means only that the request was projected into this record.
    It does not mean acknowledged, accepted, delivered, surfaced, handled,
    scheduled, executed, or completed.
    """

    observation_id: str
    request_id: str
    proposal_id: str
    kind: str
    status: RealtimeTriggerObservationStatus
    reason: str
    authority: str = (
        REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE
    )

    def __post_init__(
        self,
    ) -> None:
        for field_name in (
            "observation_id",
            "request_id",
            "proposal_id",
            "kind",
            "reason",
        ):
            if not str(
                getattr(
                    self,
                    field_name,
                )
            ).strip():
                raise ValueError(
                    f"RealtimeTriggerObservation.{field_name} cannot be blank."
                )

        if not isinstance(
            self.status,
            RealtimeTriggerObservationStatus,
        ):
            raise TypeError(
                "status must be RealtimeTriggerObservationStatus."
            )

        if (
            self.authority
            != REALTIME_TRIGGER_OBSERVATION_AUTHORITY_NONE
        ):
            raise ValueError(
                "RealtimeTriggerObservation authority is permanently NONE."
            )


def _observation_identity(
    *,
    request_id: str,
    proposal_id: str,
    kind: str,
) -> str:
    """
    Deterministic identity over privacy-minimized request references only.
    """

    payload = json.dumps(
        {
            "request_id": request_id,
            "proposal_id": proposal_id,
            "kind": kind,
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
        "rto-"
        + hashlib.sha256(
            payload
        ).hexdigest()
    )


def observe_trigger_request(
    request: RealtimeTriggerRequest,
) -> RealtimeTriggerObservation:
    """
    Project one zero-authority trigger request into an observation.

    The function is pure with respect to KUMA runtime state and performs no
    acknowledgment, delivery, wake, presentation, queue, scheduler, model,
    permission, tool, or execution side effect.
    """

    if not isinstance(
        request,
        RealtimeTriggerRequest,
    ):
        raise TypeError(
            "request must be a RealtimeTriggerRequest."
        )

    if (
        request.authority
        != REALTIME_TRIGGER_REQUEST_AUTHORITY_NONE
    ):
        raise ValueError(
            "RealtimeTriggerRequest authority must remain NONE."
        )

    request_id = str(
        request.request_id
    ).strip()

    if not request_id:
        raise ValueError(
            "request.request_id cannot be blank."
        )

    proposal_id = str(
        request.proposal_id
    ).strip()

    if not proposal_id:
        raise ValueError(
            "request.proposal_id cannot be blank."
        )

    kind = str(
        request.kind
    ).strip()

    if not kind:
        raise ValueError(
            "request.kind cannot be blank."
        )

    return RealtimeTriggerObservation(
        observation_id=_observation_identity(
            request_id=request_id,
            proposal_id=proposal_id,
            kind=kind,
        ),
        request_id=request_id,
        proposal_id=proposal_id,
        kind=kind,
        status=(
            RealtimeTriggerObservationStatus.OBSERVED
        ),
        reason=(
            "caller observed zero-authority realtime trigger request"
        ),
    )
