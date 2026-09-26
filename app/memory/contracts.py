"""Canonical zero-authority contracts for KUMA long-term memory.

MEMORY-1A is intentionally contract-only:
- no database access
- no embedding work
- no retrieval
- no agent/runtime/tool imports
- no execution authority

Persistence and migration arrive in later MEMORY-1 phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


MEMORY_AUTHORITY_NONE = "NONE"


class MemoryKind(str, Enum):
    """Semantic type of one durable long-term memory."""

    PERSONAL_FACT = "personal_fact"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"
    PROJECT_KNOWLEDGE = "project_knowledge"
    EPISODIC_EVENT = "episodic_event"
    GOAL = "goal"
    INFERENCE = "inference"
    UNCLASSIFIED = "unclassified"


class MemorySource(str, Enum):
    """Provenance class describing where a memory claim originated."""

    USER_EXPLICIT = "user_explicit"
    USER_STATEMENT = "user_statement"
    VERIFIED_SYSTEM = "verified_system"
    PROJECT_STATE = "project_state"
    IMPORTED = "imported"
    MODEL_INFERENCE = "model_inference"


class MemoryStatus(str, Enum):
    """Lifecycle status for a durable memory record."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"
    EXPIRED = "expired"


def _require_text(name: str, value: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string.")

    normalized = value.strip()

    if not normalized:
        raise ValueError(f"{name} cannot be empty.")

    return normalized


def _optional_text(name: str, value: str | None) -> str | None:
    if value is None:
        return None

    return _require_text(name, value)


def _require_unit_interval(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")

    normalized = float(value)

    if not 0.0 <= normalized <= 1.0:
        raise ValueError(
            f"{name} must be between 0.0 and 1.0."
        )

    return normalized


def _parse_iso_timestamp(
    name: str,
    value: str | None,
) -> datetime | None:
    if value is None:
        return None

    normalized = _require_text(name, value)

    try:
        return datetime.fromisoformat(
            normalized.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise ValueError(
            f"{name} must be an ISO-8601 timestamp."
        ) from error


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """Canonical descriptive record for KUMA long-term memory.

    MemoryRecord is evidence/context only. It can never authorize an
    operation, tool call, permission transition, or recovery action.
    """

    memory_id: str
    kind: MemoryKind
    category: str
    key: str
    value: str
    source: MemorySource

    confidence: float = 1.0
    importance: float = 0.5

    created_at: str = ""
    updated_at: str = ""

    observed_at: str | None = None
    valid_from: str | None = None
    valid_until: str | None = None

    status: MemoryStatus = MemoryStatus.ACTIVE
    supersedes: str | None = None

    subject: str = "user"
    project_scope: str | None = None

    authority: str = MEMORY_AUTHORITY_NONE

    def __post_init__(self) -> None:
        memory_id = _require_text(
            "memory_id",
            self.memory_id,
        )
        category = _require_text(
            "category",
            self.category,
        )
        key = _require_text(
            "key",
            self.key,
        )
        value = _require_text(
            "value",
            self.value,
        )
        subject = _require_text(
            "subject",
            self.subject,
        )

        if not isinstance(self.kind, MemoryKind):
            raise TypeError(
                "kind must be a MemoryKind."
            )

        if not isinstance(self.source, MemorySource):
            raise TypeError(
                "source must be a MemorySource."
            )

        if not isinstance(self.status, MemoryStatus):
            raise TypeError(
                "status must be a MemoryStatus."
            )

        if self.authority != MEMORY_AUTHORITY_NONE:
            raise ValueError(
                "MemoryRecord authority is permanently NONE."
            )

        confidence = _require_unit_interval(
            "confidence",
            self.confidence,
        )
        importance = _require_unit_interval(
            "importance",
            self.importance,
        )

        created_at = _require_text(
            "created_at",
            self.created_at,
        )
        updated_at = _require_text(
            "updated_at",
            self.updated_at,
        )

        created_dt = _parse_iso_timestamp(
            "created_at",
            created_at,
        )
        updated_dt = _parse_iso_timestamp(
            "updated_at",
            updated_at,
        )
        _parse_iso_timestamp(
            "observed_at",
            self.observed_at,
        )
        valid_from_dt = _parse_iso_timestamp(
            "valid_from",
            self.valid_from,
        )
        valid_until_dt = _parse_iso_timestamp(
            "valid_until",
            self.valid_until,
        )

        supersedes = _optional_text(
            "supersedes",
            self.supersedes,
        )
        project_scope = _optional_text(
            "project_scope",
            self.project_scope,
        )

        try:
            if updated_dt < created_dt:
                raise ValueError(
                    "updated_at cannot be earlier than created_at."
                )
        except TypeError as error:
            raise ValueError(
                "created_at and updated_at must use compatible timezone forms."
            ) from error

        if valid_from_dt is not None and valid_until_dt is not None:
            try:
                if valid_until_dt < valid_from_dt:
                    raise ValueError(
                        "valid_until cannot be earlier than valid_from."
                    )
            except TypeError as error:
                raise ValueError(
                    "valid_from and valid_until must use compatible timezone forms."
                ) from error

        if supersedes == memory_id:
            raise ValueError(
                "A memory cannot supersede itself."
            )

        if self.kind == MemoryKind.INFERENCE:
            if self.source != MemorySource.MODEL_INFERENCE:
                raise ValueError(
                    "Inference memories require MODEL_INFERENCE source."
                )
        elif self.source == MemorySource.MODEL_INFERENCE:
            raise ValueError(
                "MODEL_INFERENCE source must remain MemoryKind.INFERENCE."
            )

        object.__setattr__(self, "memory_id", memory_id)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "key", key)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "subject", subject)
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "importance", importance)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "supersedes", supersedes)
        object.__setattr__(self, "project_scope", project_scope)
