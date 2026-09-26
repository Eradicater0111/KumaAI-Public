from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import inspect
from pathlib import Path

import pytest

from app.agent.integrated_cognitive_loop import (
    IntegratedLoopObservation,
    IntegratedLoopStatus,
    evaluate_integrated_loop_iteration,
)
from app.agent.mission_cognitive_observation import (
    MISSION_COGNITIVE_AUTHORITY_NONE,
    MissionCognitiveObservation,
    MissionCognitiveStatus,
    project_mission_cognitive_observation,
)
from app.agent.shadow_action_evaluation import (
    evaluate_shadow_action,
)
from app.agent.shadow_cognition import (
    evaluate_shadow_cognition,
)
from app.agent.task_state import (
    TaskState,
)
from app.agent.tactical_loop import (
    TacticalLoopState,
)


ROOT = Path(__file__).resolve().parents[2]

MODULE = (
    ROOT
    / "app/agent/mission_cognitive_observation.py"
)

NOW = datetime(
    2026,
    9,
    25,
    8,
    0,
    tzinfo=timezone.utc,
)


def source():
    return MODULE.read_text()


def imports_for():
    tree = ast.parse(
        source(),
        filename=str(
            MODULE
        ),
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

        elif isinstance(
            node,
            ast.ImportFrom,
        ):
            if node.module:
                result.add(
                    node.module
                )

    return result


def calls_for():
    tree = ast.parse(
        source(),
        filename=str(
            MODULE
        ),
    )

    result = []

    for node in ast.walk(
        tree
    ):
        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        if isinstance(
            node.func,
            ast.Name,
        ):
            result.append(
                node.func.id
            )

        elif isinstance(
            node.func,
            ast.Attribute,
        ):
            result.append(
                node.func.attr
            )

    return result


def live_observation():
    tools = (
        "inspect_system",
        "execute_command",
    )

    task_state = TaskState(
        goal="Inspect current state safely."
    )

    shadow = evaluate_shadow_cognition(
        task_state=task_state,
        available_tool_names=tools,
        memory_context="",
    )

    action = evaluate_shadow_action(
        situation=shadow.situation,
        tool_name="inspect_system",
        arguments={},
        available_tool_names=tools,
    )

    return evaluate_integrated_loop_iteration(
        shadow_result=shadow,
        action_evaluation=action,
        loop_state=TacticalLoopState(),
        signals=(),
        active_goal=(
            "Inspect current state safely."
        ),
        remaining_objective="",
        mission_status="",
        seen_event_ids=(),
        acknowledged_event_ids=(),
        cues=(),
        current_time=NOW,
    )


def test_status_surface_is_exact():
    assert {
        item.name
        for item
        in MissionCognitiveStatus
    } == {
        "PROJECTED",
        "SKIPPED",
    }


def test_projection_is_frozen():
    result = (
        project_mission_cognitive_observation(
            integrated_observation=(
                live_observation()
            ),
        )
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        result.reason = "changed"


def test_projection_authority_is_none():
    result = (
        project_mission_cognitive_observation(
            integrated_observation=(
                live_observation()
            ),
        )
    )

    assert (
        result.authority
        == MISSION_COGNITIVE_AUTHORITY_NONE
        == "NONE"
    )


def test_live_observation_projects_exact_advisory_shape():
    observed = live_observation()

    result = (
        project_mission_cognitive_observation(
            integrated_observation=observed,
        )
    )

    decision = (
        observed.iteration.frame.tactical_decision
    )

    chosen = (
        decision.chosen_option
    )

    assert (
        result.status
        == MissionCognitiveStatus.PROJECTED
    )

    assert (
        result.loop_disposition
        == observed.iteration.disposition.value
    )

    assert (
        result.tactical_disposition
        == decision.disposition.value
    )

    assert (
        result.stalled
        is observed.iteration.stalled
    )

    assert result.reason

    assert (
        result.objective
        == (
            chosen.objective
            if chosen is not None
            else ""
        )
    )

    assert (
        result.expected_outcome
        == (
            chosen.expected_outcome
            if chosen is not None
            else ""
        )
    )


def test_projection_does_not_carry_source_observation():
    result = (
        project_mission_cognitive_observation(
            integrated_observation=(
                live_observation()
            ),
        )
    )

    for field_name in (
        "integrated_observation",
        "iteration",
        "frame",
        "attention_decision",
        "next_state",
    ):
        assert not hasattr(
            result,
            field_name,
        )


def test_projection_has_no_permission_execution_or_argument_surface():
    result = (
        project_mission_cognitive_observation(
            integrated_observation=(
                live_observation()
            ),
        )
    )

    for field_name in (
        "permission",
        "required_permission",
        "approved",
        "confirmation",
        "execute",
        "executor",
        "tool_name",
        "arguments",
        "handoff",
        "verified_complete",
        "retry",
        "schedule",
    ):
        assert not hasattr(
            result,
            field_name,
        )


def test_reasoning_context_is_bounded_and_declares_no_authority():
    result = (
        project_mission_cognitive_observation(
            integrated_observation=(
                live_observation()
            ),
        )
    )

    context = (
        result.to_reasoning_context()
    )

    assert context
    assert len(context) <= 2200

    assert (
        "AUTHORITY:NONE"
        in context
    )

    assert (
        "Advisory only:"
        in context
    )

    assert (
        "no permission"
        in context
    )

    assert (
        "tool-argument authority"
        in context
    )


def test_reasoning_context_excludes_option_identity_and_capability():
    observed = live_observation()

    result = (
        project_mission_cognitive_observation(
            integrated_observation=observed,
        )
    )

    context = (
        result.to_reasoning_context()
    )

    decision = (
        observed.iteration.frame.tactical_decision
    )

    chosen = (
        decision.chosen_option
    )

    if chosen is not None:
        assert (
            chosen.option_id
            not in context
        )

        if chosen.capability:
            assert (
                chosen.capability
                not in context
            )


def test_skipped_observation_projects_no_reasoning_context():
    observed = IntegratedLoopObservation(
        status=IntegratedLoopStatus.SKIPPED,
        reason=(
            "No complete current-turn cognitive pair."
        ),
        next_state=TacticalLoopState(),
    )

    result = (
        project_mission_cognitive_observation(
            integrated_observation=observed,
        )
    )

    assert (
        result.status
        == MissionCognitiveStatus.SKIPPED
    )

    assert (
        result.reason
        == "No complete current-turn cognitive pair."
    )

    assert (
        result.to_reasoning_context()
        == ""
    )


def test_wrong_source_type_fails_closed():
    with pytest.raises(
        TypeError,
        match="IntegratedLoopObservation",
    ):
        project_mission_cognitive_observation(
            integrated_observation=object(),
        )


def test_tampered_source_authority_fails_closed():
    observed = live_observation()

    object.__setattr__(
        observed,
        "authority",
        "EXECUTE",
    )

    with pytest.raises(
        ValueError,
        match="authority",
    ):
        project_mission_cognitive_observation(
            integrated_observation=observed,
        )


def test_tampered_nested_decision_authority_fails_closed():
    observed = live_observation()

    decision = (
        observed.iteration.frame.tactical_decision
    )

    object.__setattr__(
        decision,
        "authority",
        "EXECUTE",
    )

    with pytest.raises(
        ValueError,
        match="authority",
    ):
        project_mission_cognitive_observation(
            integrated_observation=observed,
        )


def test_projection_signature_is_narrow_and_keyword_only():
    signature = inspect.signature(
        project_mission_cognitive_observation
    )

    assert tuple(
        signature.parameters
    ) == (
        "integrated_observation",
    )

    parameter = (
        signature.parameters[
            "integrated_observation"
        ]
    )

    assert (
        parameter.kind
        == inspect.Parameter.KEYWORD_ONLY
    )


def test_contract_constructor_has_no_authority_input():
    signature = inspect.signature(
        MissionCognitiveObservation
    )

    assert (
        "authority"
        not in signature.parameters
    )


def test_direct_import_surface_is_narrow():
    imports = imports_for()

    assert imports == {
        "__future__",
        "dataclasses",
        "enum",
        "app.agent.cognitive_contracts",
        "app.agent.integrated_cognitive_loop",
    }


@pytest.mark.parametrize(
    "forbidden",
    (
        "app.agent.mission_service",
        "app.agent.executor",
        "app.agent.permissions",
        "app.agent.kuma_agent",
        "app.memory",
        "app.realtime.runtime",
        "app.runtime",
        "subprocess",
        "threading",
        "asyncio",
        "sqlite3",
        "requests",
        "urllib",
        "socket",
        "google.genai",
        "ollama",
    ),
)
def test_module_has_no_forbidden_direct_dependency(
    forbidden,
):
    assert (
        forbidden
        not in imports_for()
    )


def test_module_has_no_execution_or_persistence_calls():
    forbidden_calls = {
        "execute",
        "execute_mission",
        "execute_mission_step",
        "resume_mission",
        "request_confirmation",
        "register_tool",
        "save",
        "persist",
        "commit",
        "tick",
        "pending_signals",
        "chat",
        "generate",
    }

    assert (
        forbidden_calls
        .intersection(
            calls_for()
        )
        == set()
    )


def test_module_has_no_runtime_driving_loop():
    tree = ast.parse(
        source(),
        filename=str(
            MODULE
        ),
    )

    assert not any(
        isinstance(
            node,
            ast.While,
        )
        for node in ast.walk(
            tree
        )
    )


def test_boundaries_are_explicit_in_source():
    text = source()

    for marker in (
        "COGNITION != COMMAND",
        "TACTICAL DECISION != GOAL DECISION",
        "MISSION COGNITION != MISSION EXECUTION",
        "PROJECTION != PERMISSION",
        "PROJECTION != CONFIRMATION",
        "PROJECTION != COMPLETION",
        "PROJECTION != RETRY",
        "PROJECTION != PERSISTENCE",
        "NEXT STATE != SCHEDULER",
        "AUTHORITY: NONE",
    ):
        assert marker in text
