import pytest

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemorySource,
)
from app.memory.formation import (
    FormationDisposition,
    MemoryCandidate,
    MemoryDurability,
    MemorySensitivity,
    evaluate_memory_candidate,
)


def candidate(**overrides):
    values = dict(
        kind=MemoryKind.PREFERENCE,
        category="preferences",
        key="editor",
        value="Prefers VS Code.",
        source=MemorySource.USER_STATEMENT,
        durability=MemoryDurability.STABLE,
        explicit_user_authorization=False,
        confidence=1.0,
        importance=0.7,
    )
    values.update(overrides)
    return MemoryCandidate(**values)


def test_candidate_is_zero_authority():
    item = candidate()
    assert item.authority == MEMORY_AUTHORITY_NONE

    with pytest.raises(ValueError, match="authority is permanently NONE"):
        candidate(authority="EXECUTE")


def test_explicit_stable_user_memory_can_store():
    item = candidate(
        source=MemorySource.USER_EXPLICIT,
        explicit_user_authorization=True,
    )
    assert (
        evaluate_memory_candidate(item)
        == FormationDisposition.STORE_AUTHORIZED
    )


def test_implicit_stable_fact_is_candidate_only():
    assert (
        evaluate_memory_candidate(candidate())
        == FormationDisposition.CANDIDATE_ONLY
    )


def test_temporary_information_is_discarded():
    item = candidate(
        durability=MemoryDurability.TEMPORARY,
        explicit_user_authorization=True,
    )
    assert (
        evaluate_memory_candidate(item)
        == FormationDisposition.DISCARD
    )


def test_unknown_durability_is_discarded():
    item = candidate(
        durability=MemoryDurability.UNKNOWN,
        explicit_user_authorization=True,
    )
    assert (
        evaluate_memory_candidate(item)
        == FormationDisposition.DISCARD
    )


def test_sensitive_implicit_candidate_is_blocked():
    item = candidate(
        sensitivity=MemorySensitivity.SENSITIVE,
    )
    assert (
        evaluate_memory_candidate(item)
        == FormationDisposition.BLOCKED
    )


def test_model_inference_never_directly_stores():
    item = candidate(
        kind=MemoryKind.INFERENCE,
        source=MemorySource.MODEL_INFERENCE,
        explicit_user_authorization=True,
        confidence=0.55,
    )
    assert (
        evaluate_memory_candidate(item)
        == FormationDisposition.CANDIDATE_ONLY
    )


def test_imported_candidate_is_not_directly_formed():
    item = candidate(
        kind=MemoryKind.UNCLASSIFIED,
        source=MemorySource.IMPORTED,
        explicit_user_authorization=True,
    )
    assert (
        evaluate_memory_candidate(item)
        == FormationDisposition.BLOCKED
    )
