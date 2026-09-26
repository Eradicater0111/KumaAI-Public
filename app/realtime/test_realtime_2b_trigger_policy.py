from __future__ import annotations

import ast
from dataclasses import (
    FrozenInstanceError,
    fields,
)
from pathlib import Path

import pytest

from app.realtime.change_detection import (
    RealtimeRelevanceLevel,
)
from app.realtime.runtime_trigger import (
    RealtimeTriggerProposal,
)
from app.realtime.trigger_policy import (
    REALTIME_TRIGGER_POLICY_AUTHORITY_NONE,
    RealtimeTriggerEligibilityDecision,
    RealtimeTriggerEligibilityStatus,
    evaluate_trigger_eligibility,
)


ROOT = Path(__file__).resolve().parents[2]

MODULE = (
    ROOT
    / "app/realtime/trigger_policy.py"
)

TWO_A = (
    ROOT
    / "app/realtime/runtime_trigger.py"
)

TWO_A_TEST = (
    ROOT
    / "app/realtime/test_realtime_2a_runtime_trigger_boundary.py"
)

V1_REGRESSION = (
    ROOT
    / "app/realtime/test_realtime_v1_architecture_regression.py"
)


def _proposal(
    *,
    level: RealtimeRelevanceLevel = RealtimeRelevanceLevel.HIGH,
    score: float = 0.90,
    authority: str = "NONE",
) -> RealtimeTriggerProposal:
    proposal = object.__new__(
        RealtimeTriggerProposal
    )

    object.__setattr__(
        proposal,
        "proposal_id",
        "rtp-test",
    )
    object.__setattr__(
        proposal,
        "kind",
        "weather.current",
    )
    object.__setattr__(
        proposal,
        "level",
        level,
    )
    object.__setattr__(
        proposal,
        "score",
        score,
    )
    object.__setattr__(
        proposal,
        "reason",
        "precipitation started",
    )
    object.__setattr__(
        proposal,
        "authority",
        authority,
    )

    return proposal


def _field_names(
    cls,
) -> tuple[str, ...]:
    return tuple(
        item.name
        for item in fields(
            cls
        )
    )


def _imports(
    path: Path,
) -> set[str]:
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    result = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            result.update(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            result.add(
                node.module
            )

    return result


def test_2b_files_and_frozen_dependencies_exist():
    assert MODULE.is_file()
    assert TWO_A.is_file()
    assert TWO_A_TEST.is_file()
    assert V1_REGRESSION.is_file()


def test_policy_authority_constant_is_none():
    assert (
        REALTIME_TRIGGER_POLICY_AUTHORITY_NONE
        == "NONE"
    )


def test_eligibility_decision_surface_is_minimal():
    assert _field_names(
        RealtimeTriggerEligibilityDecision
    ) == (
        "proposal_id",
        "status",
        "reason",
        "authority",
    )


def test_eligibility_decision_exposes_no_action_fields():
    forbidden = {
        "tool",
        "tool_name",
        "arguments",
        "command",
        "permission",
        "confirmation",
        "execute",
        "executor",
        "callback",
        "mission",
        "retry",
        "resume",
        "wake",
        "notify",
        "verified",
        "verified_complete",
        "fact",
        "previous_fact",
        "value",
        "location",
    }

    assert set(
        _field_names(
            RealtimeTriggerEligibilityDecision
        )
    ).isdisjoint(
        forbidden
    )


def test_decision_is_frozen():
    decision = (
        evaluate_trigger_eligibility(
            _proposal(),
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=0.8,
        )
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        decision.reason = "changed"


def test_decision_rejects_non_none_authority():
    with pytest.raises(
        ValueError,
        match="permanently NONE",
    ):
        RealtimeTriggerEligibilityDecision(
            proposal_id="rtp-test",
            status=(
                RealtimeTriggerEligibilityStatus.ELIGIBLE
            ),
            reason="eligible",
            authority="USER",
        )


def test_projection_rejects_non_proposal_input():
    with pytest.raises(
        TypeError,
        match="RealtimeTriggerProposal",
    ):
        evaluate_trigger_eligibility(
            object(),
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=0.8,
        )


def test_projection_rejects_forged_proposal_authority():
    with pytest.raises(
        ValueError,
        match="authority",
    ):
        evaluate_trigger_eligibility(
            _proposal(
                authority="USER",
            ),
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=0.8,
        )


def test_minimum_level_must_be_realtime_level():
    with pytest.raises(
        TypeError,
        match="minimum_level",
    ):
        evaluate_trigger_eligibility(
            _proposal(),
            minimum_level="high",
            minimum_score=0.8,
        )


def test_ignore_cannot_be_used_as_trigger_minimum():
    with pytest.raises(
        ValueError,
        match="IGNORE",
    ):
        evaluate_trigger_eligibility(
            _proposal(),
            minimum_level=(
                RealtimeRelevanceLevel.IGNORE
            ),
            minimum_score=0.0,
        )


@pytest.mark.parametrize(
    "minimum_score",
    (
        -0.01,
        1.01,
        float("inf"),
        float("-inf"),
        float("nan"),
    ),
)
def test_minimum_score_is_bounded_and_finite(
    minimum_score,
):
    with pytest.raises(
        ValueError,
        match="minimum_score",
    ):
        evaluate_trigger_eligibility(
            _proposal(),
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=minimum_score,
        )


@pytest.mark.parametrize(
    "proposal_level,minimum_level",
    (
        (
            RealtimeRelevanceLevel.LOW,
            RealtimeRelevanceLevel.LOW,
        ),
        (
            RealtimeRelevanceLevel.MEDIUM,
            RealtimeRelevanceLevel.LOW,
        ),
        (
            RealtimeRelevanceLevel.MEDIUM,
            RealtimeRelevanceLevel.MEDIUM,
        ),
        (
            RealtimeRelevanceLevel.HIGH,
            RealtimeRelevanceLevel.LOW,
        ),
        (
            RealtimeRelevanceLevel.HIGH,
            RealtimeRelevanceLevel.MEDIUM,
        ),
        (
            RealtimeRelevanceLevel.HIGH,
            RealtimeRelevanceLevel.HIGH,
        ),
    ),
)
def test_level_meets_or_exceeds_explicit_minimum(
    proposal_level,
    minimum_level,
):
    decision = (
        evaluate_trigger_eligibility(
            _proposal(
                level=proposal_level,
                score=1.0,
            ),
            minimum_level=minimum_level,
            minimum_score=0.0,
        )
    )

    assert decision.eligible
    assert (
        decision.status
        == RealtimeTriggerEligibilityStatus.ELIGIBLE
    )


@pytest.mark.parametrize(
    "proposal_level,minimum_level",
    (
        (
            RealtimeRelevanceLevel.LOW,
            RealtimeRelevanceLevel.MEDIUM,
        ),
        (
            RealtimeRelevanceLevel.LOW,
            RealtimeRelevanceLevel.HIGH,
        ),
        (
            RealtimeRelevanceLevel.MEDIUM,
            RealtimeRelevanceLevel.HIGH,
        ),
    ),
)
def test_level_below_explicit_minimum_is_ineligible(
    proposal_level,
    minimum_level,
):
    decision = (
        evaluate_trigger_eligibility(
            _proposal(
                level=proposal_level,
                score=1.0,
            ),
            minimum_level=minimum_level,
            minimum_score=0.0,
        )
    )

    assert not decision.eligible
    assert (
        decision.status
        == RealtimeTriggerEligibilityStatus.INELIGIBLE
    )
    assert (
        "level below"
        in decision.reason
    )


def test_score_equal_to_minimum_is_eligible():
    decision = (
        evaluate_trigger_eligibility(
            _proposal(
                level=RealtimeRelevanceLevel.HIGH,
                score=0.75,
            ),
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=0.75,
        )
    )

    assert decision.eligible


def test_score_above_minimum_is_eligible():
    decision = (
        evaluate_trigger_eligibility(
            _proposal(
                level=RealtimeRelevanceLevel.HIGH,
                score=0.91,
            ),
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=0.75,
        )
    )

    assert decision.eligible


def test_score_below_minimum_is_ineligible():
    decision = (
        evaluate_trigger_eligibility(
            _proposal(
                level=RealtimeRelevanceLevel.HIGH,
                score=0.74,
            ),
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=0.75,
        )
    )

    assert not decision.eligible
    assert (
        "score below"
        in decision.reason
    )


def test_both_failed_criteria_are_reported_structurally():
    decision = (
        evaluate_trigger_eligibility(
            _proposal(
                level=RealtimeRelevanceLevel.LOW,
                score=0.2,
            ),
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=0.8,
        )
    )

    assert not decision.eligible
    assert (
        "level below"
        in decision.reason
    )
    assert (
        "score below"
        in decision.reason
    )


def test_decision_preserves_only_proposal_identity():
    proposal = _proposal()

    decision = (
        evaluate_trigger_eligibility(
            proposal,
            minimum_level=(
                RealtimeRelevanceLevel.HIGH
            ),
            minimum_score=0.8,
        )
    )

    assert (
        decision.proposal_id
        == proposal.proposal_id
    )

    assert not hasattr(
        decision,
        "kind",
    )
    assert not hasattr(
        decision,
        "score",
    )
    assert not hasattr(
        decision,
        "level",
    )


def test_policy_has_no_hidden_default_thresholds():
    source = MODULE.read_text()

    assert (
        "minimum_level:"
        in source
    )
    assert (
        "minimum_score:"
        in source
    )

    signature_fragment = (
        "proposal: RealtimeTriggerProposal,\n"
        "    *,\n"
        "    minimum_level: RealtimeRelevanceLevel,\n"
        "    minimum_score: float,"
    )

    assert signature_fragment in source


def test_2b_module_imports_only_realtime_dependencies_from_app():
    app_imports = {
        module
        for module in _imports(
            MODULE
        )
        if module.startswith(
            "app."
        )
    }

    assert app_imports == {
        "app.realtime.change_detection",
        "app.realtime.runtime_trigger",
    }


def test_2b_module_does_not_import_agent_or_tools():
    for module in _imports(
        MODULE
    ):
        assert not module.startswith(
            (
                "app.agent",
                "app.tools",
            )
        ), module


def test_2b_module_has_no_network_or_persistence_dependency():
    roots = {
        module.split(
            ".",
            1,
        )[0]
        for module in _imports(
            MODULE
        )
    }

    assert roots.isdisjoint(
        {
            "httpx",
            "requests",
            "urllib",
            "socket",
            "aiohttp",
            "websockets",
            "sqlite3",
            "sqlalchemy",
            "shelve",
        }
    )


def test_2b_module_has_no_background_execution_primitive():
    source = MODULE.read_text()

    for forbidden in (
        "threading.Thread",
        "Thread(",
        "asyncio.create_task",
        "create_task(",
        "while True",
        "run_forever(",
        "Timer(",
        "daemon=",
    ):
        assert forbidden not in source


def test_2b_module_has_no_runtime_side_effect_calls():
    source = MODULE.read_text()

    for forbidden in (
        ".tick(",
        "pending_signals(",
        "drain_signals(",
        "refresh_weather(",
        "refresh_weather_daily(",
        ".publish(",
        ".put(",
        ".register(",
        ".subscribe(",
        "emit_status(",
        ".run(",
        ".execute(",
    ):
        assert forbidden not in source


def test_2b_boundary_markers_are_explicit():
    source = MODULE.read_text()

    for marker in (
        "ELIGIBILITY != COMMAND",
        "ELIGIBILITY != PERMISSION",
        "ELIGIBILITY != WAKE",
        "ELIGIBILITY != EXECUTION",
        "ELIGIBILITY != VERIFIED COMPLETION",
        "AUTHORITY: NONE",
    ):
        assert marker in source


def test_2b_does_not_modify_frozen_2a_contract():
    source = TWO_A.read_text()

    assert (
        "class RealtimeTriggerProposal"
        in source
    )
    assert (
        "def propose_runtime_trigger("
        in source
    )
    assert (
        "TRIGGER PROPOSAL != EXECUTION"
        in source
    )


def test_2b_does_not_modify_frozen_v1_regression_contract():
    source = V1_REGRESSION.read_text()

    assert (
        "def test_realtime_v1_phase_tests_exist():"
        in source
    )
    assert (
        "def test_realtime_subsystem_has_no_background_execution_loop():"
        in source
    )
    assert (
        "def test_realtime_v1_boundary_markers_are_explicit():"
        in source
    )


def test_2b_source_compiles():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
