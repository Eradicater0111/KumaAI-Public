from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemoryRecord,
    MemorySource,
    MemoryStatus,
)


def _record(**overrides):
    values = {
        "memory_id": "mem-001",
        "kind": MemoryKind.PREFERENCE,
        "category": "preferences",
        "key": "transport",
        "value": "Prefers bike rides.",
        "source": MemorySource.USER_STATEMENT,
        "confidence": 0.95,
        "importance": 0.7,
        "created_at": "2026-09-11T12:00:00+00:00",
        "updated_at": "2026-09-11T12:00:00+00:00",
    }
    values.update(overrides)
    return MemoryRecord(**values)


def test_memory_record_is_zero_authority_and_frozen():
    record = _record()

    assert record.authority == MEMORY_AUTHORITY_NONE

    with pytest.raises(FrozenInstanceError):
        record.value = "changed"


def test_memory_record_rejects_nonzero_authority():
    with pytest.raises(
        ValueError,
        match="authority is permanently NONE",
    ):
        _record(authority="EXECUTE")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("confidence", -0.01),
        ("confidence", 1.01),
        ("importance", -0.01),
        ("importance", 1.01),
    ],
)
def test_scores_must_stay_in_unit_interval(field, value):
    with pytest.raises(ValueError):
        _record(**{field: value})


@pytest.mark.parametrize(
    "field",
    [
        "memory_id",
        "category",
        "key",
        "value",
        "subject",
        "created_at",
        "updated_at",
    ],
)
def test_required_text_fields_reject_blank_values(field):
    with pytest.raises(ValueError):
        _record(**{field: "   "})


def test_inference_cannot_masquerade_as_asserted_fact():
    with pytest.raises(
        ValueError,
        match="MODEL_INFERENCE source must remain",
    ):
        _record(
            kind=MemoryKind.PERSONAL_FACT,
            source=MemorySource.MODEL_INFERENCE,
        )


def test_inference_kind_requires_inference_source():
    with pytest.raises(
        ValueError,
        match="Inference memories require",
    ):
        _record(
            kind=MemoryKind.INFERENCE,
            source=MemorySource.USER_STATEMENT,
        )


def test_valid_inference_is_allowed_but_still_zero_authority():
    record = _record(
        kind=MemoryKind.INFERENCE,
        source=MemorySource.MODEL_INFERENCE,
        confidence=0.55,
    )

    assert record.kind == MemoryKind.INFERENCE
    assert record.authority == MEMORY_AUTHORITY_NONE


def test_memory_cannot_supersede_itself():
    with pytest.raises(
        ValueError,
        match="cannot supersede itself",
    ):
        _record(supersedes="mem-001")


def test_validity_window_cannot_run_backwards():
    with pytest.raises(
        ValueError,
        match="valid_until cannot be earlier",
    ):
        _record(
            valid_from="2026-09-12T00:00:00+00:00",
            valid_until="2026-09-11T00:00:00+00:00",
        )


def test_updated_at_cannot_predate_created_at():
    with pytest.raises(
        ValueError,
        match="updated_at cannot be earlier",
    ):
        _record(
            created_at="2026-09-12T00:00:00+00:00",
            updated_at="2026-09-11T00:00:00+00:00",
        )


def test_contract_module_has_no_runtime_execution_dependencies():
    source = Path(
        "app/memory/contracts.py"
    ).read_text()

    forbidden = (
        "app.agent",
        "app.tools",
        "app.realtime",
        "subprocess",
        "sqlite3",
        "sentence_transformers",
        "requests",
        "urllib",
        "socket",
    )

    for marker in forbidden:
        assert marker not in source


def test_contract_vocabulary_is_explicit():
    assert set(MemoryKind) == {
        MemoryKind.PERSONAL_FACT,
        MemoryKind.PREFERENCE,
        MemoryKind.RELATIONSHIP,
        MemoryKind.PROJECT_KNOWLEDGE,
        MemoryKind.EPISODIC_EVENT,
        MemoryKind.GOAL,
        MemoryKind.INFERENCE,
        MemoryKind.UNCLASSIFIED,
    }

    assert set(MemoryStatus) == {
        MemoryStatus.ACTIVE,
        MemoryStatus.SUPERSEDED,
        MemoryStatus.RETRACTED,
        MemoryStatus.EXPIRED,
    }
