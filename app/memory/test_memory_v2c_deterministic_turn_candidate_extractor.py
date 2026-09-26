from pathlib import Path

from app.memory.contracts import (
    MEMORY_AUTHORITY_NONE,
    MemoryKind,
    MemorySource,
)
from app.memory.formation import (
    FormationDisposition,
    MemoryDurability,
    MemorySensitivity,
)
from app.memory.deterministic_turn_candidate_extractor import (
    MEMORY_V2C_AUTHORITY_NONE,
    extract_deterministic_turn_memory_candidate,
)
from app.memory.turn_candidate_composition import (
    TurnCandidateCompositionStatus,
    compose_completed_turn_memory_candidate,
)


MODULE_PATH = (
    Path(__file__).resolve().parent
    / "deterministic_turn_candidate_extractor.py"
)


def extract(
    message,
):
    return (
        extract_deterministic_turn_memory_candidate(
            message
        )
    )


def test_v2c_extracts_plain_preference_literally():
    result = extract(
        "I prefer VS Code."
    )

    assert result is not None

    candidate = result.candidate

    assert candidate.kind is MemoryKind.PREFERENCE
    assert candidate.category == "preferences"
    assert candidate.key == "preference_vs_code"
    assert candidate.value == "VS Code"
    assert candidate.source is MemorySource.USER_STATEMENT
    assert candidate.durability is MemoryDurability.STABLE
    assert candidate.sensitivity is MemorySensitivity.NORMAL
    assert candidate.explicit_user_authorization is False
    assert candidate.authority == MEMORY_AUTHORITY_NONE
    assert result.authority == MEMORY_V2C_AUTHORITY_NONE


def test_v2c_extracts_favorite_with_semantic_label_key():
    result = extract(
        "My favorite editor is VS Code."
    )

    assert result is not None
    assert result.candidate.kind is MemoryKind.PREFERENCE
    assert result.candidate.category == "preferences"
    assert result.candidate.key == "favorite_editor"
    assert result.candidate.value == "VS Code"


def test_v2c_extracts_name_as_personal_fact():
    result = extract(
        "My name is Suprreeth."
    )

    assert result is not None
    assert result.candidate.kind is MemoryKind.PERSONAL_FACT
    assert result.candidate.category == "personal"
    assert result.candidate.key == "name"
    assert result.candidate.value == "Suprreeth"


def test_v2c_extracts_project_identity_without_paraphrase():
    result = extract(
        "KUMA is my desktop AI project."
    )

    assert result is not None
    assert result.candidate.kind is MemoryKind.PROJECT_KNOWLEDGE
    assert result.candidate.category == "projects"
    assert result.candidate.key == "kuma_project"
    assert (
        result.candidate.value
        == "KUMA is my desktop AI project"
    )

    assert (
        result.evidence_text
        == "KUMA is my desktop AI project"
    )


def test_v2c_preserves_literal_value_case():
    result = extract(
        "My favorite editor is VS CoDe."
    )

    assert result is not None
    assert result.candidate.value == "VS CoDe"


def test_v2c_integrates_with_frozen_v2b_and_v2a():
    result = compose_completed_turn_memory_candidate(
        user_message="I prefer VS Code.",
        explicit_memory_write_requested=False,
        extractor=(
            extract_deterministic_turn_memory_candidate
        ),
    )

    assert (
        result.status
        is TurnCandidateCompositionStatus.OBSERVED
    )

    assert result.observation is not None

    assert (
        result.observation.disposition
        is FormationDisposition.CANDIDATE_ONLY
    )

    assert result.authority == MEMORY_AUTHORITY_NONE


def test_v2c_question_returns_no_candidate():
    assert (
        extract(
            "My favorite editor is VS Code?"
        )
        is None
    )


def test_v2c_temporary_today_statement_returns_no_candidate():
    assert (
        extract(
            "I prefer VS Code today."
        )
        is None
    )


def test_v2c_currently_statement_returns_no_candidate():
    assert (
        extract(
            "I currently prefer VS Code."
        )
        is None
    )


def test_v2c_uncertain_future_statement_returns_no_candidate():
    assert (
        extract(
            "I might use VS Code later."
        )
        is None
    )


def test_v2c_compound_statement_returns_no_candidate():
    assert (
        extract(
            "My favorite editor is VS Code and my theme is dark."
        )
        is None
    )


def test_v2c_explicit_remember_request_returns_no_candidate():
    assert (
        extract(
            "Remember that I prefer VS Code."
        )
        is None
    )


def test_v2c_keep_in_mind_request_returns_no_candidate():
    assert (
        extract(
            "Keep in mind that KUMA is my desktop AI project."
        )
        is None
    )


def test_v2c_secret_like_content_returns_no_candidate():
    assert (
        extract(
            "I prefer password secret123."
        )
        is None
    )


def test_v2c_statement_about_other_person_returns_no_candidate():
    assert (
        extract(
            "Alice prefers VS Code."
        )
        is None
    )


def test_v2c_casual_statement_returns_no_candidate():
    assert (
        extract(
            "That was funny."
        )
        is None
    )


def test_v2c_empty_message_returns_no_candidate():
    assert extract("   ") is None


def test_v2c_non_string_fails_closed():
    try:
        extract(None)
    except TypeError as error:
        assert "must be a string" in str(
            error
        )
    else:
        raise AssertionError(
            "Expected TypeError."
        )


def test_v2c_candidate_value_is_exact_user_substring():
    message = (
        "My favorite editor is VS Code."
    )

    result = extract(
        message
    )

    assert result is not None
    assert result.candidate.value in message
    assert result.evidence_text in message


def test_v2c_project_candidate_value_is_exact_user_substring():
    message = (
        "KUMA is my desktop AI project."
    )

    result = extract(
        message
    )

    assert result is not None
    assert result.candidate.value in message
    assert result.evidence_text in message


def test_v2c_has_no_persistence_permission_agent_or_model_dependency():
    source = MODULE_PATH.read_text()

    forbidden = (
        "app.memory.store",
        "app.memory.manager",
        "app.memory.memory",
        "sqlite3",
        "PermissionLevel",
        "KumaAgent",
        "app.runtime",
        "app.integration",
        "app.realtime",
        "app.brain",
        "ask_model",
        "ollama",
    )

    for item in forbidden:
        assert item not in source


def test_v2c_markers_preserve_policy_boundary():
    source = MODULE_PATH.read_text()

    for marker in (
        "PRECISION > RECALL",
        "USER MESSAGE = ONLY FACTUAL EVIDENCE",
        "LITERAL MATCH != INFERENCE",
        "EXTRACTION != PERSISTENCE",
        "EXTRACTION != PERMISSION",
        "CANDIDATE KEY != DURABLE REVISION IDENTITY",
        "EXPLICIT MEMORY REQUEST != IMPLICIT CANDIDATE",
        "TEMPORARY STATE != STABLE MEMORY",
        "COMPOUND STATEMENT != SINGLE CANDIDATE",
        "SECRET-LIKE CONTENT != IMPLICIT CANDIDATE",
        "MODEL CALL = NONE",
        "AUTHORITY: NONE",
    ):
        assert marker in source
