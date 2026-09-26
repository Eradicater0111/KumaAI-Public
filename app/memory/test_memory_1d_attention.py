from datetime import datetime, timedelta, timezone

from app.memory.attention import (
    SEMANTIC_FLOOR,
    score_memory_attention,
)
from app.memory.contracts import (
    MemoryKind,
    MemoryRecord,
    MemorySource,
    MemoryStatus,
)


NOW = datetime(
    2026,
    9,
    12,
    0,
    0,
    tzinfo=timezone.utc,
)


def _record(
    memory_id,
    *,
    kind,
    source,
    confidence,
    importance,
    age_days,
    status=MemoryStatus.ACTIVE,
    project_scope=None,
):
    timestamp = (
        NOW
        - timedelta(
            days=age_days
        )
    ).isoformat()

    return MemoryRecord(
        memory_id=memory_id,
        kind=kind,
        category="probe",
        key=memory_id,
        value=memory_id,
        source=source,
        confidence=confidence,
        importance=importance,
        created_at=timestamp,
        updated_at=timestamp,
        status=status,
        project_scope=project_scope,
    )


def _score(
    record,
    similarity,
):
    return score_memory_attention(
        record,
        similarity,
        now=NOW,
    ).attention_score


def test_weak_inference_loses_to_explicit_preference():
    weak_inference = _record(
        "weak-inference",
        kind=MemoryKind.INFERENCE,
        source=MemorySource.MODEL_INFERENCE,
        confidence=0.35,
        importance=0.20,
        age_days=120,
    )

    explicit_preference = _record(
        "explicit-preference",
        kind=MemoryKind.PREFERENCE,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=0.90,
        age_days=2,
    )

    assert (
        _score(
            explicit_preference,
            0.93,
        )
        > _score(
            weak_inference,
            0.98,
        )
    )


def test_recent_project_fact_beats_slightly_more_similar_old_fact():
    old_project = _record(
        "old-project",
        kind=MemoryKind.PROJECT_KNOWLEDGE,
        source=MemorySource.PROJECT_STATE,
        confidence=0.90,
        importance=0.45,
        age_days=180,
    )

    recent_project = _record(
        "recent-project",
        kind=MemoryKind.PROJECT_KNOWLEDGE,
        source=MemorySource.PROJECT_STATE,
        confidence=0.98,
        importance=0.95,
        age_days=(4 / 24),
    )

    assert (
        _score(
            recent_project,
            0.89,
        )
        > _score(
            old_project,
            0.91,
        )
    )


def test_current_explicit_fact_beats_legacy_import():
    legacy = _record(
        "legacy",
        kind=MemoryKind.UNCLASSIFIED,
        source=MemorySource.IMPORTED,
        confidence=0.50,
        importance=0.50,
        age_days=300,
    )

    current = _record(
        "current",
        kind=MemoryKind.PERSONAL_FACT,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=0.80,
        age_days=(2 / 24),
    )

    assert (
        _score(
            current,
            0.86,
        )
        > _score(
            legacy,
            0.88,
        )
    )


def test_metadata_cannot_rescue_barely_related_memory():
    perfect_metadata = _record(
        "perfect",
        kind=MemoryKind.PERSONAL_FACT,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=1.0,
        age_days=0,
    )

    weak_metadata = _record(
        "weak",
        kind=MemoryKind.INFERENCE,
        source=MemorySource.MODEL_INFERENCE,
        confidence=0.0,
        importance=0.0,
        age_days=3650,
    )

    assert (
        _score(
            weak_metadata,
            0.70,
        )
        > _score(
            perfect_metadata,
            0.30,
        )
    )


def test_attention_is_bounded_by_semantic_similarity():
    record = _record(
        "bounded",
        kind=MemoryKind.PREFERENCE,
        source=MemorySource.USER_STATEMENT,
        confidence=0.80,
        importance=0.60,
        age_days=20,
    )

    result = score_memory_attention(
        record,
        0.80,
        now=NOW,
    )

    assert (
        0.80 * SEMANTIC_FLOOR
        <= result.attention_score
        <= 0.80
    )

    assert (
        SEMANTIC_FLOOR
        <= result.multiplier
        <= 1.0
    )


def test_status_and_project_scope_do_not_change_attention_score():
    base = _record(
        "base",
        kind=MemoryKind.PROJECT_KNOWLEDGE,
        source=MemorySource.PROJECT_STATE,
        confidence=0.90,
        importance=0.80,
        age_days=5,
        status=MemoryStatus.ACTIVE,
        project_scope="KumaAI",
    )

    expired = _record(
        "expired",
        kind=MemoryKind.PROJECT_KNOWLEDGE,
        source=MemorySource.PROJECT_STATE,
        confidence=0.90,
        importance=0.80,
        age_days=5,
        status=MemoryStatus.EXPIRED,
        project_scope="OtherProject",
    )

    assert (
        _score(base, 0.90)
        == _score(expired, 0.90)
    )


def test_attention_breakdown_is_auditable():
    record = _record(
        "audit",
        kind=MemoryKind.PREFERENCE,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=0.90,
        age_days=2,
    )

    result = score_memory_attention(
        record,
        0.93,
        now=NOW,
    )

    assert result.similarity == 0.93
    assert result.confidence == 1.0
    assert result.importance == 0.90

    for value in (
        result.recency,
        result.source,
        result.kind,
        result.metadata_quality,
        result.multiplier,
    ):
        assert 0.0 <= value <= 1.0


def test_future_updated_timestamp_receives_no_super_recency_bonus():
    future = _record(
        "future",
        kind=MemoryKind.PREFERENCE,
        source=MemorySource.USER_EXPLICIT,
        confidence=1.0,
        importance=1.0,
        age_days=-30,
    )

    result = score_memory_attention(
        future,
        0.90,
        now=NOW,
    )

    assert result.recency == 1.0
    assert result.attention_score <= 0.90
