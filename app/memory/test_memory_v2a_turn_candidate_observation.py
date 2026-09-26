from dataclasses import FrozenInstanceError
from pathlib import Path

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
)
from app.memory.turn_candidate_observation import (
    CompletedTurnMemoryCandidateObservation,
    MEMORY_V2A_AUTHORITY_NONE,
    observe_completed_turn_memory_candidate,
)


MODULE_PATH = (
    Path(__file__).resolve().parent
    / "turn_candidate_observation.py"
)


def candidate(
    **overrides,
):
    values = dict(
        kind=MemoryKind.PREFERENCE,
        category="preferences",
        key="editor",
        value="VS Code",
        source=MemorySource.USER_STATEMENT,
        durability=MemoryDurability.STABLE,
        explicit_user_authorization=False,
        confidence=1.0,
        importance=0.7,
    )

    values.update(
        overrides
    )

    return MemoryCandidate(
        **values
    )


def observe(
    item=None,
    *,
    user_message="I prefer VS Code.",
    evidence_text="VS Code",
):
    return (
        observe_completed_turn_memory_candidate(
            user_message=user_message,
            evidence_text=evidence_text,
            candidate=(
                item
                if item is not None
                else candidate()
            ),
        )
    )


def test_v2a_stable_implicit_statement_is_candidate_only():
    result = observe()

    assert isinstance(
        result,
        CompletedTurnMemoryCandidateObservation,
    )

    assert (
        result.disposition
        is FormationDisposition.CANDIDATE_ONLY
    )

    assert result.authority == MEMORY_AUTHORITY_NONE
    assert result.authority == MEMORY_V2A_AUTHORITY_NONE


def test_v2a_preserves_exact_candidate_identity():
    item = candidate()

    result = observe(
        item
    )

    assert result.candidate is item


def test_v2a_temporary_information_is_discarded():
    result = observe(
        candidate(
            durability=MemoryDurability.TEMPORARY,
        )
    )

    assert (
        result.disposition
        is FormationDisposition.DISCARD
    )


def test_v2a_unknown_durability_is_discarded():
    result = observe(
        candidate(
            durability=MemoryDurability.UNKNOWN,
        )
    )

    assert (
        result.disposition
        is FormationDisposition.DISCARD
    )


def test_v2a_sensitive_implicit_statement_is_blocked():
    result = observe(
        candidate(
            sensitivity=MemorySensitivity.SENSITIVE,
        )
    )

    assert (
        result.disposition
        is FormationDisposition.BLOCKED
    )


def test_v2a_requires_exact_user_message_grounding():
    with pytest.raises(
        ValueError,
        match="exact substring",
    ):
        observe(
            user_message="I prefer VS Code.",
            evidence_text="Neovim",
        )


def test_v2a_rejects_user_explicit_source():
    with pytest.raises(
        ValueError,
        match="USER_STATEMENT",
    ):
        observe(
            candidate(
                source=MemorySource.USER_EXPLICIT,
                explicit_user_authorization=True,
            )
        )


def test_v2a_rejects_explicit_authorization_even_without_explicit_source():
    with pytest.raises(
        ValueError,
        match="explicitly authorized",
    ):
        observe(
            candidate(
                explicit_user_authorization=True,
            )
        )


def test_v2a_rejects_model_inference():
    with pytest.raises(
        ValueError,
        match="USER_STATEMENT",
    ):
        observe(
            candidate(
                kind=MemoryKind.INFERENCE,
                source=MemorySource.MODEL_INFERENCE,
                confidence=0.5,
            )
        )


def test_v2a_observation_is_immutable():
    result = observe()

    with pytest.raises(
        FrozenInstanceError,
    ):
        result.user_message = "changed"


def test_v2a_has_no_persistence_or_execution_dependencies():
    source = MODULE_PATH.read_text()

    forbidden = (
        "MemoryStore",
        "app.memory.store",
        "app.memory.manager",
        "app.memory.memory",
        "remember(",
        "save_memory(",
        "sqlite3",
        "PermissionLevel",
        "executor",
        "tool_registry",
        "app.runtime",
        "app.integration",
        "app.realtime",
    )

    for item in forbidden:
        assert item not in source


def test_v2a_markers_preserve_separation_of_powers():
    source = MODULE_PATH.read_text()

    for marker in (
        "CANDIDATE != DURABLE MEMORY",
        "CANDIDATE != PERMISSION",
        "FORMATION != PERSISTENCE",
        "OBSERVATION != MEMORY WRITE",
        "USER STATEMENT != USER AUTHORIZATION",
        "ASSISTANT OUTPUT != USER FACT",
        "TOOL OUTPUT != MEMORY",
        "REALTIME EVIDENCE != MEMORY",
        "MODEL INFERENCE != USER STATEMENT",
        "AUTHORITY: NONE",
    ):
        assert marker in source
