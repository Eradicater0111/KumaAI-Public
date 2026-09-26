"""Bounded attention scoring for KUMA MEMORY-1D.

Semantic similarity remains the retrieval foundation. Memory metadata may
only discount/re-order already-relevant candidates; it never bypasses the
semantic threshold or creates execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.memory.contracts import (
    MemoryKind,
    MemoryRecord,
    MemorySource,
)


SEMANTIC_FLOOR = 0.60
METADATA_SHARE = 0.40
RECENCY_WINDOW_DAYS = 30.0

CONFIDENCE_WEIGHT = 0.35
IMPORTANCE_WEIGHT = 0.25
RECENCY_WEIGHT = 0.20
SOURCE_WEIGHT = 0.10
KIND_WEIGHT = 0.10


_SOURCE_FACTOR = {
    MemorySource.USER_EXPLICIT: 1.00,
    MemorySource.USER_STATEMENT: 0.95,
    MemorySource.VERIFIED_SYSTEM: 0.95,
    MemorySource.PROJECT_STATE: 0.90,
    MemorySource.IMPORTED: 0.60,
    MemorySource.MODEL_INFERENCE: 0.50,
}


_KIND_FACTOR = {
    MemoryKind.PERSONAL_FACT: 1.00,
    MemoryKind.PREFERENCE: 1.00,
    MemoryKind.RELATIONSHIP: 0.95,
    MemoryKind.PROJECT_KNOWLEDGE: 0.95,
    MemoryKind.GOAL: 0.90,
    MemoryKind.EPISODIC_EVENT: 0.85,
    MemoryKind.UNCLASSIFIED: 0.70,
    MemoryKind.INFERENCE: 0.55,
}


@dataclass(frozen=True, slots=True)
class AttentionBreakdown:
    """Auditable components used to rank one eligible memory."""

    similarity: float
    confidence: float
    importance: float
    recency: float
    source: float
    kind: float
    metadata_quality: float
    multiplier: float
    attention_score: float


def _normalize_now(
    now: datetime | None,
) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)

    if not isinstance(now, datetime):
        raise TypeError(
            "now must be datetime or None."
        )

    if now.tzinfo is None:
        now = now.replace(
            tzinfo=timezone.utc
        )

    return now.astimezone(
        timezone.utc
    )


def _parse_timestamp(
    value: str,
) -> datetime:
    parsed = datetime.fromisoformat(
        str(value).replace(
            "Z",
            "+00:00",
        )
    )

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def recency_factor(
    updated_at: str,
    *,
    now: datetime | None = None,
) -> float:
    """Return a smooth 0..1 freshness factor.

    The curve is 1 / (1 + age_days / 30). Future timestamps caused by
    small clock skew are clamped to age zero rather than receiving a bonus.
    """

    current_time = _normalize_now(now)
    updated = _parse_timestamp(updated_at)

    age_seconds = max(
        0.0,
        (
            current_time
            - updated
        ).total_seconds(),
    )

    age_days = (
        age_seconds
        / 86400.0
    )

    return 1.0 / (
        1.0
        + age_days
        / RECENCY_WINDOW_DAYS
    )


def source_factor(
    source: MemorySource,
) -> float:
    if not isinstance(
        source,
        MemorySource,
    ):
        raise TypeError(
            "source must be MemorySource."
        )

    return _SOURCE_FACTOR[
        source
    ]


def kind_factor(
    kind: MemoryKind,
) -> float:
    if not isinstance(
        kind,
        MemoryKind,
    ):
        raise TypeError(
            "kind must be MemoryKind."
        )

    return _KIND_FACTOR[
        kind
    ]


def score_memory_attention(
    record: MemoryRecord,
    similarity: float,
    *,
    now: datetime | None = None,
) -> AttentionBreakdown:
    """Compute bounded attention for an already-eligible memory.

    Semantic similarity is multiplied by a factor in [0.60, 1.00].
    Metadata may demote/re-order close semantic matches but can never
    increase a candidate beyond its raw semantic similarity.
    """

    if not isinstance(
        record,
        MemoryRecord,
    ):
        raise TypeError(
            "record must be a MemoryRecord."
        )

    if (
        isinstance(similarity, bool)
        or not isinstance(
            similarity,
            (int, float),
        )
    ):
        raise TypeError(
            "similarity must be numeric."
        )

    similarity = float(
        similarity
    )

    if not -1.0 <= similarity <= 1.0:
        raise ValueError(
            "similarity must be between -1.0 and 1.0."
        )

    confidence = float(
        record.confidence
    )
    importance = float(
        record.importance
    )
    recency = recency_factor(
        record.updated_at,
        now=now,
    )
    source = source_factor(
        record.source
    )
    kind = kind_factor(
        record.kind
    )

    metadata_quality = (
        CONFIDENCE_WEIGHT
        * confidence
        + IMPORTANCE_WEIGHT
        * importance
        + RECENCY_WEIGHT
        * recency
        + SOURCE_WEIGHT
        * source
        + KIND_WEIGHT
        * kind
    )

    multiplier = (
        SEMANTIC_FLOOR
        + METADATA_SHARE
        * metadata_quality
    )

    attention_score = (
        similarity
        * multiplier
    )

    return AttentionBreakdown(
        similarity=similarity,
        confidence=confidence,
        importance=importance,
        recency=recency,
        source=source,
        kind=kind,
        metadata_quality=metadata_quality,
        multiplier=multiplier,
        attention_score=attention_score,
    )
