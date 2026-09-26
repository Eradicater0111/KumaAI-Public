from __future__ import annotations

from dataclasses import dataclass, field

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemorySource,
)
from app.memory.formation import (
    FormationDisposition,
    MemoryCandidate,
    evaluate_memory_candidate,
)


MEMORY_V2A_AUTHORITY_NONE = (
    MEMORY_AUTHORITY_NONE
)


# =========================================================
# KUMA MEMORY-V2A — IMPLICIT COMPLETED-TURN CANDIDATE OBSERVATION
# =========================================================
#
# EXPLICIT COMPLETED USER TURN
#   -> CALLER-SUPPLIED, USER-GROUNDED MemoryCandidate
#   -> FROZEN MEMORY-1E FORMATION POLICY
#   -> CANDIDATE_ONLY / DISCARD / BLOCKED
#   -> STOP
#
# CANDIDATE != DURABLE MEMORY
# CANDIDATE != PERMISSION
# FORMATION != PERSISTENCE
# OBSERVATION != MEMORY WRITE
# USER STATEMENT != USER AUTHORIZATION
# ASSISTANT OUTPUT != USER FACT
# TOOL OUTPUT != MEMORY
# REALTIME EVIDENCE != MEMORY
# MODEL INFERENCE != USER STATEMENT
# AUTHORITY: NONE
#
# Memory-V2A deliberately has:
#   - no typed durable-store dependency,
#   - no explicit memory-write manager dependency,
#   - no legacy durable-write helper dependency,
#   - no SQLite access,
#   - no tool execution,
#   - no permission mutation,
#   - no runtime/integration ownership.
#
# Explicit USER_AUTHORIZED durable persistence remains owned by
# the existing remember tool path.
# =========================================================


def _require_text(
    name: str,
    value: object,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise TypeError(
            f"{name} must be a string."
        )

    normalized = value.strip()

    if not normalized:
        raise ValueError(
            f"{name} must not be blank."
        )

    return normalized


@dataclass(
    frozen=True,
    slots=True,
)
class CompletedTurnMemoryCandidateObservation:
    """
    Zero-authority observation of one already-constructed implicit
    memory candidate grounded in the current user's own message.

    This carrier never persists the candidate.
    """

    user_message: str
    evidence_text: str
    candidate: MemoryCandidate
    disposition: FormationDisposition
    authority: str = field(
        default=MEMORY_V2A_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        user_message = _require_text(
            "user_message",
            self.user_message,
        )

        evidence_text = _require_text(
            "evidence_text",
            self.evidence_text,
        )

        if evidence_text not in user_message:
            raise ValueError(
                "evidence_text must be an exact substring of user_message."
            )

        if not isinstance(
            self.candidate,
            MemoryCandidate,
        ):
            raise TypeError(
                "candidate must be a MemoryCandidate."
            )

        if not isinstance(
            self.disposition,
            FormationDisposition,
        ):
            raise TypeError(
                "disposition must be a FormationDisposition."
            )

        if (
            self.authority
            != MEMORY_V2A_AUTHORITY_NONE
        ):
            raise ValueError(
                "Memory-V2A observation authority is permanently NONE."
            )

        if (
            self.candidate.authority
            != MEMORY_V2A_AUTHORITY_NONE
        ):
            raise ValueError(
                "Memory-V2A candidate authority must remain NONE."
            )

        if (
            self.candidate.source
            is not MemorySource.USER_STATEMENT
        ):
            raise ValueError(
                "Memory-V2A accepts only implicit USER_STATEMENT candidates."
            )

        if (
            self.candidate.explicit_user_authorization
            is not False
        ):
            raise ValueError(
                "Memory-V2A cannot consume an explicitly authorized memory write."
            )

        if (
            self.disposition
            is FormationDisposition.STORE_AUTHORIZED
        ):
            raise ValueError(
                "Memory-V2A cannot produce STORE_AUTHORIZED."
            )

        object.__setattr__(
            self,
            "user_message",
            user_message,
        )

        object.__setattr__(
            self,
            "evidence_text",
            evidence_text,
        )


def observe_completed_turn_memory_candidate(
    *,
    user_message: str,
    evidence_text: str,
    candidate: MemoryCandidate,
) -> CompletedTurnMemoryCandidateObservation:
    """
    Evaluate one implicit, user-authored memory candidate without writing it.

    The caller is responsible for candidate extraction/classification.
    Memory-V2A only proves grounding and delegates disposition to the frozen
    Memory-1E formation policy.
    """

    if not isinstance(
        candidate,
        MemoryCandidate,
    ):
        raise TypeError(
            "candidate must be a MemoryCandidate."
        )

    if (
        candidate.source
        is not MemorySource.USER_STATEMENT
    ):
        raise ValueError(
            "Memory-V2A accepts only implicit USER_STATEMENT candidates."
        )

    if (
        candidate.explicit_user_authorization
        is not False
    ):
        raise ValueError(
            "Memory-V2A cannot consume an explicitly authorized memory write."
        )

    disposition = (
        evaluate_memory_candidate(
            candidate
        )
    )

    if (
        disposition
        is FormationDisposition.STORE_AUTHORIZED
    ):
        raise ValueError(
            "Memory-V2A cannot produce STORE_AUTHORIZED."
        )

    return (
        CompletedTurnMemoryCandidateObservation(
            user_message=user_message,
            evidence_text=evidence_text,
            candidate=candidate,
            disposition=disposition,
        )
    )
