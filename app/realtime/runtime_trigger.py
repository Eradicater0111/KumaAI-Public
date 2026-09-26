from __future__ import annotations

"""
KUMA REALTIME-2A — zero-authority runtime trigger proposal boundary.

This module does not wake KUMA, start background work, call tools, grant
permission, refresh providers, mutate realtime state, or execute actions.

It only projects one already-existing RealtimeSignal into a bounded,
privacy-minimized trigger proposal that a future caller-owned policy layer
may choose to inspect.

TRIGGER PROPOSAL != COMMAND
TRIGGER PROPOSAL != PERMISSION
TRIGGER PROPOSAL != EXECUTION
TRIGGER PROPOSAL != VERIFIED COMPLETION
AUTHORITY: NONE
"""

from dataclasses import dataclass
import hashlib
import json
import math

from app.realtime.change_detection import (
    REALTIME_SIGNAL_AUTHORITY_NONE,
    RealtimeRelevanceLevel,
    RealtimeSignal,
)


REALTIME_TRIGGER_AUTHORITY_NONE = "NONE"
MAX_TRIGGER_REASON_CHARS = 160


@dataclass(frozen=True, slots=True)
class RealtimeTriggerProposal:
    """
    Privacy-minimized zero-authority proposal derived from one realtime signal.

    The proposal contains relevance metadata only. It carries no fact value,
    location, tool, callback, permission, execution request, or completion
    claim.
    """

    proposal_id: str
    kind: str
    level: RealtimeRelevanceLevel
    score: float
    reason: str
    authority: str = REALTIME_TRIGGER_AUTHORITY_NONE

    def __post_init__(self) -> None:
        if not str(self.proposal_id).strip():
            raise ValueError(
                "RealtimeTriggerProposal.proposal_id cannot be blank."
            )

        if not str(self.kind).strip():
            raise ValueError(
                "RealtimeTriggerProposal.kind cannot be blank."
            )

        if not isinstance(
            self.level,
            RealtimeRelevanceLevel,
        ):
            raise TypeError(
                "RealtimeTriggerProposal.level must be RealtimeRelevanceLevel."
            )

        score = float(
            self.score
        )

        if (
            not math.isfinite(score)
            or not 0.0 <= score <= 1.0
        ):
            raise ValueError(
                "RealtimeTriggerProposal.score must be finite and between 0.0 and 1.0."
            )

        if not str(self.reason).strip():
            raise ValueError(
                "RealtimeTriggerProposal.reason cannot be blank."
            )

        if len(self.reason) > MAX_TRIGGER_REASON_CHARS:
            raise ValueError(
                "RealtimeTriggerProposal.reason exceeds the bounded length."
            )

        if self.authority != REALTIME_TRIGGER_AUTHORITY_NONE:
            raise ValueError(
                "RealtimeTriggerProposal authority is permanently NONE."
            )


def _clean_reason(
    value: object,
) -> str:
    clean = " ".join(
        str(value).split()
    )

    if not clean:
        clean = (
            "existing realtime signal is eligible "
            "for future trigger-policy inspection"
        )

    return clean[
        :MAX_TRIGGER_REASON_CHARS
    ]


def _proposal_identity(
    *,
    kind: str,
    level: RealtimeRelevanceLevel,
    score: float,
    reason: str,
) -> str:
    """
    Deterministic identity over privacy-minimized proposal metadata only.

    Raw RealtimeFact value/location content is intentionally excluded.
    """

    payload = json.dumps(
        {
            "kind": kind,
            "level": level.value,
            "score": float(score),
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
        "rtp-"
        + hashlib.sha256(
            payload
        ).hexdigest()
    )


def propose_runtime_trigger(
    signal: RealtimeSignal,
) -> RealtimeTriggerProposal | None:
    """
    Project one existing realtime signal into a zero-authority proposal.

    IGNORE/zero-score signals produce no proposal. Every other existing
    relevance level is projected without inventing a stronger score or
    making an execution decision.

    This function is pure with respect to KUMA runtime state.
    """

    if not isinstance(
        signal,
        RealtimeSignal,
    ):
        raise TypeError(
            "signal must be a RealtimeSignal."
        )

    if (
        signal.authority
        != REALTIME_SIGNAL_AUTHORITY_NONE
    ):
        raise ValueError(
            "RealtimeSignal authority must remain NONE."
        )

    fact = signal.fact

    if getattr(
        fact,
        "authority",
        None,
    ) != REALTIME_TRIGGER_AUTHORITY_NONE:
        raise ValueError(
            "RealtimeSignal fact authority must remain NONE."
        )

    previous = signal.previous_fact

    if (
        previous is not None
        and getattr(
            previous,
            "authority",
            None,
        )
        != REALTIME_TRIGGER_AUTHORITY_NONE
    ):
        raise ValueError(
            "Previous RealtimeFact authority must remain NONE."
        )

    if not isinstance(
        signal.level,
        RealtimeRelevanceLevel,
    ):
        raise TypeError(
            "signal.level must be RealtimeRelevanceLevel."
        )

    score = float(
        signal.score
    )

    if (
        not math.isfinite(score)
        or not 0.0 <= score <= 1.0
    ):
        raise ValueError(
            "signal.score must be finite and between 0.0 and 1.0."
        )

    if (
        signal.level
        == RealtimeRelevanceLevel.IGNORE
        or score <= 0.0
    ):
        return None

    kind = str(
        signal.kind
    ).strip()

    if not kind:
        raise ValueError(
            "signal.kind cannot be blank."
        )

    reason = _clean_reason(
        signal.reason
    )

    return RealtimeTriggerProposal(
        proposal_id=_proposal_identity(
            kind=kind,
            level=signal.level,
            score=score,
            reason=reason,
        ),
        kind=kind,
        level=signal.level,
        score=score,
        reason=reason,
    )
