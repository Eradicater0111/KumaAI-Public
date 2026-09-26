from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemorySource,
)
from app.memory.formation import (
    MemoryCandidate,
)
from app.memory.turn_candidate_observation import (
    CompletedTurnMemoryCandidateObservation,
    observe_completed_turn_memory_candidate,
)


MEMORY_V2B_AUTHORITY_NONE = (
    MEMORY_AUTHORITY_NONE
)


# =========================================================
# KUMA MEMORY-V2B — CALLER-OWNED COMPLETED-TURN COMPOSITION
# =========================================================
#
# CURRENT USER MESSAGE
#   + EXPLICIT WRITE-PATH CLASSIFICATION
#   + CALLER-SUPPLIED BOUNDED EXTRACTOR
#   -> ZERO OR ONE EXACT-GROUNDED USER_STATEMENT CANDIDATE
#   -> FROZEN MEMORY-V2A OBSERVATION
#   -> STOP
#
# USER MESSAGE = ONLY FACTUAL EVIDENCE
# EXTRACTOR != MEMORY AUTHORITY
# EXTRACTION != PERSISTENCE
# CANDIDATE != DURABLE MEMORY
# CANDIDATE != PERMISSION
# EXPLICIT MEMORY WRITE PATH != IMPLICIT EXTRACTION
# ASSISTANT RESPONSE != MEMORY EVIDENCE
# TOOL RESULT != MEMORY EVIDENCE
# REALTIME SIGNAL != MEMORY EVIDENCE
# SCRATCHPAD != MEMORY EVIDENCE
# FAILURE != USER-TURN FAILURE
# AUTHORITY: NONE
#
# This module intentionally owns no durable-store, tool, agent, runtime,
# integration, realtime, or model dependency.
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


class TurnCandidateCompositionStatus(
    str,
    Enum,
):
    SKIPPED_EXPLICIT_MEMORY_WRITE = (
        "skipped_explicit_memory_write"
    )
    NO_CANDIDATE = "no_candidate"
    OBSERVED = "observed"
    FAILED = "failed"


@dataclass(
    frozen=True,
    slots=True,
)
class ExtractedTurnMemoryCandidate:
    """
    One caller-produced implicit memory candidate plus exact user evidence.

    The carrier itself does not decide whether the candidate is useful and
    does not persist anything.
    """

    evidence_text: str
    candidate: MemoryCandidate
    authority: str = field(
        default=MEMORY_V2B_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        evidence_text = _require_text(
            "evidence_text",
            self.evidence_text,
        )

        if not isinstance(
            self.candidate,
            MemoryCandidate,
        ):
            raise TypeError(
                "candidate must be a MemoryCandidate."
            )

        if (
            self.authority
            != MEMORY_V2B_AUTHORITY_NONE
        ):
            raise ValueError(
                "Memory-V2B extraction authority is permanently NONE."
            )

        if (
            self.candidate.authority
            != MEMORY_V2B_AUTHORITY_NONE
        ):
            raise ValueError(
                "Memory-V2B candidate authority must remain NONE."
            )

        if (
            self.candidate.source
            is not MemorySource.USER_STATEMENT
        ):
            raise ValueError(
                "Memory-V2B accepts only implicit USER_STATEMENT candidates."
            )

        if (
            self.candidate.explicit_user_authorization
            is not False
        ):
            raise ValueError(
                "Memory-V2B cannot consume an explicitly authorized memory write."
            )

        object.__setattr__(
            self,
            "evidence_text",
            evidence_text,
        )


@dataclass(
    frozen=True,
    slots=True,
)
class CompletedTurnMemoryCandidateComposition:
    """
    Fail-soft outcome of one bounded implicit candidate extraction attempt.
    """

    status: TurnCandidateCompositionStatus
    observation: (
        CompletedTurnMemoryCandidateObservation
        | None
    ) = None
    reason: str = ""
    authority: str = field(
        default=MEMORY_V2B_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.status,
            TurnCandidateCompositionStatus,
        ):
            raise TypeError(
                "status must be a TurnCandidateCompositionStatus."
            )

        if (
            self.authority
            != MEMORY_V2B_AUTHORITY_NONE
        ):
            raise ValueError(
                "Memory-V2B composition authority is permanently NONE."
            )

        if (
            self.status
            is TurnCandidateCompositionStatus.OBSERVED
        ):
            if not isinstance(
                self.observation,
                CompletedTurnMemoryCandidateObservation,
            ):
                raise ValueError(
                    "OBSERVED composition requires a Memory-V2A observation."
                )

        elif self.observation is not None:
            raise ValueError(
                "Non-OBSERVED composition cannot carry an observation."
            )

        if (
            self.status
            is TurnCandidateCompositionStatus.FAILED
        ):
            _require_text(
                "reason",
                self.reason,
            )


TurnMemoryCandidateExtractor = Callable[
    [str],
    ExtractedTurnMemoryCandidate | None,
]


def compose_completed_turn_memory_candidate(
    *,
    user_message: str,
    explicit_memory_write_requested: bool,
    extractor: TurnMemoryCandidateExtractor,
) -> CompletedTurnMemoryCandidateComposition:
    """
    Run one caller-owned implicit extraction attempt and stop at Memory-V2A.

    The user message is the only factual evidence admitted here.
    """

    normalized_user_message = _require_text(
        "user_message",
        user_message,
    )

    if type(
        explicit_memory_write_requested
    ) is not bool:
        raise TypeError(
            "explicit_memory_write_requested must be a bool."
        )

    if not callable(
        extractor
    ):
        raise TypeError(
            "extractor must be callable."
        )

    if explicit_memory_write_requested:
        return (
            CompletedTurnMemoryCandidateComposition(
                status=(
                    TurnCandidateCompositionStatus
                    .SKIPPED_EXPLICIT_MEMORY_WRITE
                ),
            )
        )

    try:
        extracted = extractor(
            normalized_user_message
        )
    except Exception as error:
        return (
            CompletedTurnMemoryCandidateComposition(
                status=(
                    TurnCandidateCompositionStatus.FAILED
                ),
                reason=(
                    "extractor_failed:"
                    + type(error).__name__
                ),
            )
        )

    if extracted is None:
        return (
            CompletedTurnMemoryCandidateComposition(
                status=(
                    TurnCandidateCompositionStatus.NO_CANDIDATE
                ),
            )
        )

    if not isinstance(
        extracted,
        ExtractedTurnMemoryCandidate,
    ):
        return (
            CompletedTurnMemoryCandidateComposition(
                status=(
                    TurnCandidateCompositionStatus.FAILED
                ),
                reason="extractor_invalid_result",
            )
        )

    try:
        if (
            extracted.evidence_text
            not in normalized_user_message
        ):
            raise ValueError(
                "evidence_not_grounded"
            )

        candidate_value = _require_text(
            "candidate.value",
            extracted.candidate.value,
        )

        if (
            candidate_value
            not in normalized_user_message
        ):
            raise ValueError(
                "candidate_value_not_grounded"
            )

        observation = (
            observe_completed_turn_memory_candidate(
                user_message=(
                    normalized_user_message
                ),
                evidence_text=(
                    extracted.evidence_text
                ),
                candidate=(
                    extracted.candidate
                ),
            )
        )

    except Exception as error:
        return (
            CompletedTurnMemoryCandidateComposition(
                status=(
                    TurnCandidateCompositionStatus.FAILED
                ),
                reason=(
                    "observation_failed:"
                    + type(error).__name__
                ),
            )
        )

    return (
        CompletedTurnMemoryCandidateComposition(
            status=(
                TurnCandidateCompositionStatus.OBSERVED
            ),
            observation=observation,
        )
    )
