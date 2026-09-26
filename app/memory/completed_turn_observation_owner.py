from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Generic, TypeVar

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
)
from app.memory.deterministic_turn_candidate_extractor import (
    extract_deterministic_turn_memory_candidate,
)
from app.memory.turn_candidate_composition import (
    CompletedTurnMemoryCandidateComposition,
    TurnMemoryCandidateExtractor,
    compose_completed_turn_memory_candidate,
)


_ResultT = TypeVar(
    "_ResultT"
)

MEMORY_V2D_AUTHORITY_NONE = (
    MEMORY_AUTHORITY_NONE
)


# =========================================================
# KUMA MEMORY-V2D — COMPLETED-TURN OBSERVATION OWNER
# =========================================================
#
# ALREADY-EXPLICIT CALLER OPERATION
#   + CURRENT USER MESSAGE
#   + CALLER-OWNED EXPLICIT-MEMORY-OPERATION CLASSIFICATION
#   -> OPERATION EXACTLY ONCE
#   -> IF SUCCESSFUL, FAIL-SOFT MEMORY-V2C/B/A OBSERVATION
#   -> RETURN EXACT OPERATION RESULT
#
# OPERATION != MEMORY OBSERVATION
# RESPONSE != MEMORY EVIDENCE
# USER MESSAGE = ONLY MEMORY EVIDENCE
# COMPLETION != PERSISTENCE
# OBSERVATION FAILURE != USER-TURN FAILURE
# EXPLICIT MEMORY OPERATION != IMPLICIT EXTRACTION
# INVALID REQUEST != MEMORY CANDIDATE
# ONE RUN CALL = ONE CALLER OPERATION
# OWNER != PERMISSION
# OWNER != PERSISTENCE
# OWNER != RUNTIME
# OWNER != INTEGRATION
# AUTHORITY: NONE
#
# The owner never receives the assistant response as extraction input.
# It stores only the latest bounded observation outcome in process memory.
# =========================================================


class CompletedTurnObservationStatus(
    str,
    Enum,
):
    COMPOSED = "composed"
    SKIPPED_INVALID_REQUEST = (
        "skipped_invalid_request"
    )
    SKIPPED_EXPLICIT_MEMORY_OPERATION = (
        "skipped_explicit_memory_operation"
    )
    FAILED = "failed"


@dataclass(
    frozen=True,
    slots=True,
)
class CompletedTurnMemoryObservation:
    status: CompletedTurnObservationStatus
    composition: (
        CompletedTurnMemoryCandidateComposition
        | None
    ) = None
    reason: str = ""
    authority: str = field(
        default=MEMORY_V2D_AUTHORITY_NONE,
        init=False,
    )

    def __post_init__(
        self,
    ) -> None:
        if not isinstance(
            self.status,
            CompletedTurnObservationStatus,
        ):
            raise TypeError(
                "status must be a CompletedTurnObservationStatus."
            )

        if (
            self.authority
            != MEMORY_V2D_AUTHORITY_NONE
        ):
            raise ValueError(
                "Memory-V2D observation authority is permanently NONE."
            )

        if (
            self.status
            is CompletedTurnObservationStatus.COMPOSED
        ):
            if not isinstance(
                self.composition,
                CompletedTurnMemoryCandidateComposition,
            ):
                raise ValueError(
                    "COMPOSED observation requires a Memory-V2B composition."
                )

        elif self.composition is not None:
            raise ValueError(
                "Non-COMPOSED observation cannot carry a composition."
            )

        if (
            self.status
            is CompletedTurnObservationStatus.FAILED
        ):
            if not isinstance(
                self.reason,
                str,
            ) or not self.reason.strip():
                raise ValueError(
                    "FAILED observation requires a nonblank reason."
                )


class KumaMemoryV2CompletedTurnOwner(
    Generic[_ResultT],
):
    """
    Own one fail-soft post-completion memory observation at a time.

    The caller still owns intent, permission, execution, and the operation.
    """

    def __init__(
        self,
        *,
        extractor: TurnMemoryCandidateExtractor = (
            extract_deterministic_turn_memory_candidate
        ),
    ) -> None:
        if not callable(
            extractor
        ):
            raise TypeError(
                "extractor must be callable."
            )

        self._extractor = extractor
        self._last_observation: (
            CompletedTurnMemoryObservation
            | None
        ) = None

    @property
    def authority(
        self,
    ) -> str:
        return MEMORY_V2D_AUTHORITY_NONE

    def last_observation(
        self,
    ) -> CompletedTurnMemoryObservation | None:
        return self._last_observation

    def run(
        self,
        operation: Callable[[], _ResultT],
        *,
        user_message: object,
        explicit_memory_operation_requested: bool,
    ) -> _ResultT:
        """
        Run the caller operation exactly once, then observe completion.

        Operation exceptions propagate unchanged and do not create a memory
        observation. Memory-observation failures are isolated from a successful
        operation result.
        """

        if not callable(
            operation
        ):
            raise TypeError(
                "operation must be callable."
            )

        if type(
            explicit_memory_operation_requested
        ) is not bool:
            raise TypeError(
                "explicit_memory_operation_requested must be a bool."
            )

        self._last_observation = None

        result = operation()

        if not isinstance(
            user_message,
            str,
        ):
            self._last_observation = (
                CompletedTurnMemoryObservation(
                    status=(
                        CompletedTurnObservationStatus
                        .SKIPPED_INVALID_REQUEST
                    ),
                )
            )

            return result

        normalized_user_message = (
            user_message.strip()
        )

        if not normalized_user_message:
            self._last_observation = (
                CompletedTurnMemoryObservation(
                    status=(
                        CompletedTurnObservationStatus
                        .SKIPPED_INVALID_REQUEST
                    ),
                )
            )

            return result

        if explicit_memory_operation_requested:
            self._last_observation = (
                CompletedTurnMemoryObservation(
                    status=(
                        CompletedTurnObservationStatus
                        .SKIPPED_EXPLICIT_MEMORY_OPERATION
                    ),
                )
            )

            return result

        try:
            composition = (
                compose_completed_turn_memory_candidate(
                    user_message=(
                        normalized_user_message
                    ),
                    explicit_memory_write_requested=False,
                    extractor=self._extractor,
                )
            )

            self._last_observation = (
                CompletedTurnMemoryObservation(
                    status=(
                        CompletedTurnObservationStatus
                        .COMPOSED
                    ),
                    composition=composition,
                )
            )

        except Exception as error:
            self._last_observation = (
                CompletedTurnMemoryObservation(
                    status=(
                        CompletedTurnObservationStatus
                        .FAILED
                    ),
                    reason=(
                        "memory_observation_failed:"
                        + type(error).__name__
                    ),
                )
            )

        return result
