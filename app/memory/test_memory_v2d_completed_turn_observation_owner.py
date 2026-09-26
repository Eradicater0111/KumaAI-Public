from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
)
from app.memory.formation import (
    FormationDisposition,
)
from app.memory.completed_turn_observation_owner import (
    CompletedTurnMemoryObservation,
    CompletedTurnObservationStatus,
    KumaMemoryV2CompletedTurnOwner,
    MEMORY_V2D_AUTHORITY_NONE,
)
from app.memory.turn_candidate_composition import (
    TurnCandidateCompositionStatus,
)


MODULE_PATH = (
    Path(__file__).resolve().parent
    / "completed_turn_observation_owner.py"
)


def owner(
    **kwargs,
):
    return KumaMemoryV2CompletedTurnOwner(
        **kwargs
    )


def test_v2d_runs_caller_operation_exactly_once():
    calls = []
    expected = object()

    def operation():
        calls.append(
            "run"
        )
        return expected

    memory_owner = owner()

    result = memory_owner.run(
        operation,
        user_message="I prefer VS Code.",
        explicit_memory_operation_requested=False,
    )

    assert result is expected
    assert calls == ["run"]


def test_v2d_plain_preference_composes_v2c_v2b_v2a():
    memory_owner = owner()

    result = memory_owner.run(
        lambda: "assistant-response",
        user_message="I prefer VS Code.",
        explicit_memory_operation_requested=False,
    )

    assert result == "assistant-response"

    observation = (
        memory_owner.last_observation()
    )

    assert isinstance(
        observation,
        CompletedTurnMemoryObservation,
    )

    assert (
        observation.status
        is CompletedTurnObservationStatus.COMPOSED
    )

    composition = (
        observation.composition
    )

    assert composition is not None

    assert (
        composition.status
        is TurnCandidateCompositionStatus.OBSERVED
    )

    assert composition.observation is not None

    assert (
        composition.observation.disposition
        is FormationDisposition.CANDIDATE_ONLY
    )

    assert (
        composition.observation.candidate.value
        == "VS Code"
    )

    assert observation.authority == MEMORY_AUTHORITY_NONE
    assert observation.authority == MEMORY_V2D_AUTHORITY_NONE
    assert memory_owner.authority == MEMORY_AUTHORITY_NONE


def test_v2d_response_is_not_passed_to_extractor():
    seen = []

    def extractor(
        message,
    ):
        seen.append(
            message
        )
        return None

    memory_owner = owner(
        extractor=extractor
    )

    result = memory_owner.run(
        lambda: "PRIVATE ASSISTANT RESPONSE",
        user_message="I prefer VS Code.",
        explicit_memory_operation_requested=False,
    )

    assert result == "PRIVATE ASSISTANT RESPONSE"
    assert seen == [
        "I prefer VS Code.",
    ]

    assert (
        "PRIVATE ASSISTANT RESPONSE"
        not in repr(
            memory_owner.last_observation()
        )
    )


def test_v2d_explicit_memory_operation_skips_extractor():
    calls = []

    def extractor(
        message,
    ):
        calls.append(
            message
        )
        raise AssertionError(
            "extractor must not run"
        )

    memory_owner = owner(
        extractor=extractor
    )

    result = memory_owner.run(
        lambda: "remembered",
        user_message=(
            "Remember that I prefer VS Code."
        ),
        explicit_memory_operation_requested=True,
    )

    assert result == "remembered"
    assert calls == []

    observation = (
        memory_owner.last_observation()
    )

    assert observation is not None

    assert (
        observation.status
        is (
            CompletedTurnObservationStatus
            .SKIPPED_EXPLICIT_MEMORY_OPERATION
        )
    )


@pytest.mark.parametrize(
    "message",
    (
        "",
        "   ",
        None,
    ),
)
def test_v2d_invalid_or_empty_request_skips_memory_observation(
    message,
):
    calls = []

    def extractor(
        _message,
    ):
        calls.append(
            "called"
        )
        return None

    memory_owner = owner(
        extractor=extractor
    )

    result = memory_owner.run(
        lambda: "response",
        user_message=message,
        explicit_memory_operation_requested=False,
    )

    assert result == "response"
    assert calls == []

    observation = (
        memory_owner.last_observation()
    )

    assert observation is not None

    assert (
        observation.status
        is (
            CompletedTurnObservationStatus
            .SKIPPED_INVALID_REQUEST
        )
    )


def test_v2d_extractor_failure_does_not_change_successful_response():
    def extractor(
        _message,
    ):
        raise RuntimeError(
            "boom"
        )

    memory_owner = owner(
        extractor=extractor
    )

    result = memory_owner.run(
        lambda: "success",
        user_message="I prefer VS Code.",
        explicit_memory_operation_requested=False,
    )

    assert result == "success"

    observation = (
        memory_owner.last_observation()
    )

    assert observation is not None

    assert (
        observation.status
        is CompletedTurnObservationStatus.COMPOSED
    )

    assert observation.composition is not None

    assert (
        observation.composition.status
        is TurnCandidateCompositionStatus.FAILED
    )

    assert (
        observation.composition.reason
        == "extractor_failed:RuntimeError"
    )


def test_v2d_unexpected_composition_exception_is_fail_soft(
    monkeypatch,
):
    import app.memory.completed_turn_observation_owner as module

    def fail(
        **_kwargs,
    ):
        raise RuntimeError(
            "unexpected"
        )

    monkeypatch.setattr(
        module,
        "compose_completed_turn_memory_candidate",
        fail,
    )

    memory_owner = owner()

    result = memory_owner.run(
        lambda: "success",
        user_message="I prefer VS Code.",
        explicit_memory_operation_requested=False,
    )

    assert result == "success"

    observation = (
        memory_owner.last_observation()
    )

    assert observation is not None

    assert (
        observation.status
        is CompletedTurnObservationStatus.FAILED
    )

    assert (
        observation.reason
        == "memory_observation_failed:RuntimeError"
    )


def test_v2d_operation_failure_propagates_and_creates_no_observation():
    memory_owner = owner()

    def operation():
        raise LookupError(
            "operation failed"
        )

    with pytest.raises(
        LookupError,
        match="operation failed",
    ):
        memory_owner.run(
            operation,
            user_message="I prefer VS Code.",
            explicit_memory_operation_requested=False,
        )

    assert (
        memory_owner.last_observation()
        is None
    )


def test_v2d_last_observation_is_bounded_replacement():
    memory_owner = owner()

    memory_owner.run(
        lambda: "first",
        user_message="I prefer VS Code.",
        explicit_memory_operation_requested=False,
    )

    first = (
        memory_owner.last_observation()
    )

    memory_owner.run(
        lambda: "second",
        user_message="ordinary conversation",
        explicit_memory_operation_requested=False,
    )

    second = (
        memory_owner.last_observation()
    )

    assert first is not None
    assert second is not None
    assert second is not first

    assert (
        second.status
        is CompletedTurnObservationStatus.COMPOSED
    )

    assert second.composition is not None

    assert (
        second.composition.status
        is TurnCandidateCompositionStatus.NO_CANDIDATE
    )


def test_v2d_observation_is_immutable():
    memory_owner = owner()

    memory_owner.run(
        lambda: "response",
        user_message="ordinary conversation",
        explicit_memory_operation_requested=False,
    )

    observation = (
        memory_owner.last_observation()
    )

    assert observation is not None

    with pytest.raises(
        FrozenInstanceError,
    ):
        observation.reason = "changed"


def test_v2d_strict_bool_for_explicit_memory_operation_flag():
    memory_owner = owner()

    with pytest.raises(
        TypeError,
        match="must be a bool",
    ):
        memory_owner.run(
            lambda: "response",
            user_message="I prefer VS Code.",
            explicit_memory_operation_requested=1,
        )


def test_v2d_rejects_noncallable_operation_before_any_observation():
    memory_owner = owner()

    with pytest.raises(
        TypeError,
        match="operation must be callable",
    ):
        memory_owner.run(
            None,
            user_message="I prefer VS Code.",
            explicit_memory_operation_requested=False,
        )

    assert (
        memory_owner.last_observation()
        is None
    )


def test_v2d_source_has_no_persistence_agent_runtime_integration_or_model_dependency():
    source = MODULE_PATH.read_text()

    forbidden = (
        "app.memory.store",
        "app.memory.manager",
        "app.memory.memory",
        "sqlite3",
        "PermissionLevel",
        "KumaAgent",
        "gui_runtime",
        "kuma_runtime",
        "app.runtime",
        "app.integration",
        "app.realtime",
        "app.brain",
        "ask_model",
        "ollama",
    )

    for item in forbidden:
        assert item not in source


def test_v2d_source_never_accepts_assistant_response_as_memory_input():
    source = MODULE_PATH.read_text()

    assert "assistant_response" not in source
    assert "response_text" not in source


def test_v2d_markers_preserve_separation_of_powers():
    source = MODULE_PATH.read_text()

    for marker in (
        "OPERATION != MEMORY OBSERVATION",
        "RESPONSE != MEMORY EVIDENCE",
        "USER MESSAGE = ONLY MEMORY EVIDENCE",
        "COMPLETION != PERSISTENCE",
        "OBSERVATION FAILURE != USER-TURN FAILURE",
        "EXPLICIT MEMORY OPERATION != IMPLICIT EXTRACTION",
        "INVALID REQUEST != MEMORY CANDIDATE",
        "ONE RUN CALL = ONE CALLER OPERATION",
        "OWNER != PERMISSION",
        "OWNER != PERSISTENCE",
        "OWNER != RUNTIME",
        "OWNER != INTEGRATION",
        "AUTHORITY: NONE",
    ):
        assert marker in source
