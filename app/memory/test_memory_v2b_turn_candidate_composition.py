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
from app.memory.turn_candidate_composition import (
    CompletedTurnMemoryCandidateComposition,
    ExtractedTurnMemoryCandidate,
    MEMORY_V2B_AUTHORITY_NONE,
    TurnCandidateCompositionStatus,
    compose_completed_turn_memory_candidate,
)


MODULE_PATH = (
    Path(__file__).resolve().parent
    / "turn_candidate_composition.py"
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


def extracted(
    item=None,
    *,
    evidence_text="VS Code",
):
    return ExtractedTurnMemoryCandidate(
        evidence_text=evidence_text,
        candidate=(
            item
            if item is not None
            else candidate()
        ),
    )


def compose(
    extractor,
    *,
    user_message="I prefer VS Code.",
    explicit_memory_write_requested=False,
):
    return compose_completed_turn_memory_candidate(
        user_message=user_message,
        explicit_memory_write_requested=(
            explicit_memory_write_requested
        ),
        extractor=extractor,
    )


def test_v2b_observes_one_exact_grounded_stable_candidate():
    item = candidate()

    result = compose(
        lambda _message: extracted(
            item
        )
    )

    assert isinstance(
        result,
        CompletedTurnMemoryCandidateComposition,
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.OBSERVED
    )

    assert result.observation is not None
    assert result.observation.candidate is item

    assert (
        result.observation.disposition
        is FormationDisposition.CANDIDATE_ONLY
    )

    assert result.authority == MEMORY_AUTHORITY_NONE
    assert result.authority == MEMORY_V2B_AUTHORITY_NONE


def test_v2b_invokes_extractor_exactly_once():
    calls = []

    def extractor(
        message,
    ):
        calls.append(
            message
        )

        return extracted()

    result = compose(
        extractor
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.OBSERVED
    )

    assert calls == [
        "I prefer VS Code.",
    ]


def test_v2b_none_means_no_candidate():
    result = compose(
        lambda _message: None
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.NO_CANDIDATE
    )

    assert result.observation is None


def test_v2b_explicit_memory_write_path_skips_extractor():
    calls = []

    def extractor(
        _message,
    ):
        calls.append(
            "called"
        )

        return extracted()

    result = compose(
        extractor,
        user_message=(
            "Remember that I prefer VS Code."
        ),
        explicit_memory_write_requested=True,
    )

    assert (
        result.status
        is (
            TurnCandidateCompositionStatus
            .SKIPPED_EXPLICIT_MEMORY_WRITE
        )
    )

    assert result.observation is None
    assert calls == []


def test_v2b_extractor_failure_is_isolated():
    def extractor(
        _message,
    ):
        raise RuntimeError(
            "boom"
        )

    result = compose(
        extractor
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.FAILED
    )

    assert (
        result.reason
        == "extractor_failed:RuntimeError"
    )

    assert result.observation is None


def test_v2b_invalid_extractor_result_is_isolated():
    result = compose(
        lambda _message: "not-a-candidate"
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.FAILED
    )

    assert (
        result.reason
        == "extractor_invalid_result"
    )


def test_v2b_requires_evidence_to_be_in_current_user_message():
    result = compose(
        lambda _message: extracted(
            evidence_text="Neovim",
        )
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.FAILED
    )

    assert result.reason.startswith(
        "observation_failed:"
    )


def test_v2b_requires_candidate_value_to_be_in_current_user_message():
    result = compose(
        lambda _message: extracted(
            candidate(
                value="Neovim",
            ),
            evidence_text="I prefer",
        )
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.FAILED
    )

    assert result.reason.startswith(
        "observation_failed:"
    )


def test_v2b_preserves_memory_v2a_discard():
    result = compose(
        lambda _message: extracted(
            candidate(
                durability=MemoryDurability.TEMPORARY,
            )
        )
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.OBSERVED
    )

    assert (
        result.observation.disposition
        is FormationDisposition.DISCARD
    )


def test_v2b_preserves_memory_v2a_block():
    result = compose(
        lambda _message: extracted(
            candidate(
                sensitivity=MemorySensitivity.SENSITIVE,
            )
        )
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.OBSERVED
    )

    assert (
        result.observation.disposition
        is FormationDisposition.BLOCKED
    )


def test_v2b_extracted_carrier_rejects_explicit_memory_source():
    with pytest.raises(
        ValueError,
        match="USER_STATEMENT",
    ):
        extracted(
            candidate(
                source=MemorySource.USER_EXPLICIT,
                explicit_user_authorization=True,
            )
        )


def test_v2b_extracted_carrier_rejects_model_inference():
    with pytest.raises(
        ValueError,
        match="USER_STATEMENT",
    ):
        extracted(
            candidate(
                kind=MemoryKind.INFERENCE,
                source=MemorySource.MODEL_INFERENCE,
                confidence=0.5,
            )
        )


def test_v2b_result_is_immutable():
    result = compose(
        lambda _message: None
    )

    with pytest.raises(
        FrozenInstanceError,
    ):
        result.reason = "changed"


def test_v2b_requires_strict_bool_for_explicit_write_path():
    with pytest.raises(
        TypeError,
        match="must be a bool",
    ):
        compose_completed_turn_memory_candidate(
            user_message="I prefer VS Code.",
            explicit_memory_write_requested=1,
            extractor=lambda _message: None,
        )


def test_v2b_has_no_persistence_execution_or_model_dependencies():
    source = MODULE_PATH.read_text()

    forbidden = (
        "app.memory.store",
        "app.memory.manager",
        "app.memory.memory",
        "sqlite3",
        "PermissionLevel",
        "KumaAgent",
        "executor",
        "tool_registry",
        "app.runtime",
        "app.integration",
        "app.realtime",
        "app.brain",
        "ask_model",
        "ollama",
    )

    for item in forbidden:
        assert item not in source


def test_v2b_markers_preserve_separation_of_powers():
    source = MODULE_PATH.read_text()

    for marker in (
        "USER MESSAGE = ONLY FACTUAL EVIDENCE",
        "EXTRACTOR != MEMORY AUTHORITY",
        "EXTRACTION != PERSISTENCE",
        "CANDIDATE != DURABLE MEMORY",
        "CANDIDATE != PERMISSION",
        "EXPLICIT MEMORY WRITE PATH != IMPLICIT EXTRACTION",
        "ASSISTANT RESPONSE != MEMORY EVIDENCE",
        "TOOL RESULT != MEMORY EVIDENCE",
        "REALTIME SIGNAL != MEMORY EVIDENCE",
        "SCRATCHPAD != MEMORY EVIDENCE",
        "FAILURE != USER-TURN FAILURE",
        "AUTHORITY: NONE",
    ):
        assert marker in source
