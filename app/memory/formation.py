"""KUMA MEMORY-1E controlled memory-formation policy.

This module classifies proposed memories only. It never persists data,
invokes tools, or grants execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemorySource,
)


class MemoryDurability(str, Enum):
    STABLE = "stable"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class MemorySensitivity(str, Enum):
    NORMAL = "normal"
    SENSITIVE = "sensitive"


class FormationDisposition(str, Enum):
    STORE_AUTHORIZED = "store_authorized"
    CANDIDATE_ONLY = "candidate_only"
    DISCARD = "discard"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class MemoryCandidate:
    kind: MemoryKind
    category: str
    key: str
    value: str
    source: MemorySource
    durability: MemoryDurability
    sensitivity: MemorySensitivity = MemorySensitivity.NORMAL
    explicit_user_authorization: bool = False
    confidence: float = 1.0
    importance: float = 0.5
    authority: str = MEMORY_AUTHORITY_NONE

    def __post_init__(self) -> None:
        for name in ("category", "key", "value"):
            value = getattr(self, name)
            if type(value) is not str:
                raise TypeError(f"{name} must be a string.")
            value = value.strip()
            if not value:
                raise ValueError(f"{name} cannot be empty.")
            object.__setattr__(self, name, value)

        if not isinstance(self.kind, MemoryKind):
            raise TypeError("kind must be MemoryKind.")
        if not isinstance(self.source, MemorySource):
            raise TypeError("source must be MemorySource.")
        if not isinstance(self.durability, MemoryDurability):
            raise TypeError("durability must be MemoryDurability.")
        if not isinstance(self.sensitivity, MemorySensitivity):
            raise TypeError("sensitivity must be MemorySensitivity.")
        if type(self.explicit_user_authorization) is not bool:
            raise TypeError("explicit_user_authorization must be bool.")

        for name in ("confidence", "importance"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be numeric.")
            value = float(value)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0.0 and 1.0.")
            object.__setattr__(self, name, value)

        if self.authority != MEMORY_AUTHORITY_NONE:
            raise ValueError("MemoryCandidate authority is permanently NONE.")

        if self.kind == MemoryKind.INFERENCE:
            if self.source != MemorySource.MODEL_INFERENCE:
                raise ValueError(
                    "Inference candidates require MODEL_INFERENCE source."
                )
        elif self.source == MemorySource.MODEL_INFERENCE:
            raise ValueError(
                "MODEL_INFERENCE source must remain MemoryKind.INFERENCE."
            )


def evaluate_memory_candidate(
    candidate: MemoryCandidate,
) -> FormationDisposition:
    """Return formation policy without writing anything."""

    if not isinstance(candidate, MemoryCandidate):
        raise TypeError("candidate must be MemoryCandidate.")

    if candidate.durability == MemoryDurability.TEMPORARY:
        return FormationDisposition.DISCARD

    if (
        candidate.sensitivity == MemorySensitivity.SENSITIVE
        and not candidate.explicit_user_authorization
    ):
        return FormationDisposition.BLOCKED

    if (
        candidate.kind == MemoryKind.INFERENCE
        or candidate.source == MemorySource.MODEL_INFERENCE
    ):
        return FormationDisposition.CANDIDATE_ONLY

    if candidate.durability == MemoryDurability.UNKNOWN:
        return FormationDisposition.DISCARD

    if not candidate.explicit_user_authorization:
        return FormationDisposition.CANDIDATE_ONLY

    if candidate.source not in {
        MemorySource.USER_EXPLICIT,
        MemorySource.USER_STATEMENT,
        MemorySource.VERIFIED_SYSTEM,
        MemorySource.PROJECT_STATE,
    }:
        return FormationDisposition.BLOCKED

    return FormationDisposition.STORE_AUTHORIZED
