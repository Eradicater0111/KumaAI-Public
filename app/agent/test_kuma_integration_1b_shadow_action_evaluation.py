from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import inspect
from pathlib import Path

import pytest

from app.agent.cognitive_contracts import (
    TacticalDisposition,
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.permissions import (
    PermissionLevel,
    require_explicit_permission,
)
from app.agent.shadow_action_evaluation import (
    ShadowActionEvaluation,
    ShadowActionStatus,
    arguments_digest,
    evaluate_shadow_action,
)


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "app/agent/kuma_agent.py"
MODULE = ROOT / "app/agent/shadow_action_evaluation.py"

NOW = datetime(
    2026,
    9,
    13,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_situation(
    *,
    goal="Inspect current state safely.",
    capabilities=(
        "system_inspection",
        "terminal",
    ),
):
    snapshot = WorldStateSnapshot(
        timestamp=NOW.isoformat(),
        task_goal=goal,
        system_state=(
            "system: ready",
        ),
    )

    return TacticalSituation(
        goal=goal,
        observed_state=(
            "system ready",
        ),
        known_facts=(
            "registered tools exist",
        ),
        uncertainties=(),
        constraints=(),
        available_capabilities=capabilities,
        world_state=snapshot,
    )


def agent_source():
    return AGENT.read_text()


def module_source():
    return MODULE.read_text()


def imports_for(path: Path):
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    result = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(
                alias.name
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                result.add(node.module)

    return result


def calls_for(path: Path):
    tree = ast.parse(
        path.read_text(),
        filename=str(path),
    )

    result = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            result.append(
                node.func.id
            )

        elif isinstance(node.func, ast.Attribute):
            result.append(
                node.func.attr
            )

    return result


def evaluated(
    *,
    tool_name="inspect_system",
    arguments=None,
    available_tool_names=None,
):
    if arguments is None:
        arguments = {}

    if available_tool_names is None:
        available_tool_names = (
            "inspect_system",
            "execute_command",
        )

    return evaluate_shadow_action(
        situation=make_situation(),
        tool_name=tool_name,
        arguments=arguments,
        available_tool_names=available_tool_names,
    )


def test_status_surface_is_exact():
    assert {
        item.name
        for item in ShadowActionStatus
    } == {
        "EVALUATED",
        "UNAVAILABLE",
    }


def test_evaluated_result_is_frozen():
    result = evaluated()

    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"


def test_evaluated_result_authority_is_none():
    result = evaluated()

    assert result.authority == "NONE"


def test_evaluated_candidate_authority_is_none():
    result = evaluated()

    assert result.candidate is not None
    assert result.candidate.authority == "NONE"
    assert result.candidate.option.authority == "NONE"


def test_evaluated_decision_authority_is_none():
    result = evaluated()

    assert result.decision is not None
    assert result.decision.authority == "NONE"


def test_safe_tool_is_evaluated():
    result = evaluated(
        tool_name="inspect_system",
    )

    assert (
        result.status
        == ShadowActionStatus.EVALUATED
    )


def test_dangerous_tool_is_evaluated_without_authorizing():
    result = evaluated(
        tool_name="execute_command",
        arguments={
            "command": "echo hello",
        },
    )

    assert (
        result.status
        == ShadowActionStatus.EVALUATED
    )
    assert result.authority == "NONE"
    assert (
        result.candidate.option.required_permission
        == PermissionLevel.DANGEROUS
    )


def test_safe_tool_permission_metadata_matches_kuma():
    result = evaluated(
        tool_name="inspect_system",
    )

    assert (
        result.candidate.option.required_permission
        == require_explicit_permission(
            "inspect_system"
        )
    )


def test_dangerous_tool_permission_metadata_matches_kuma():
    result = evaluated(
        tool_name="execute_command",
        arguments={
            "command": "echo hello",
        },
    )

    assert (
        result.candidate.option.required_permission
        == require_explicit_permission(
            "execute_command"
        )
    )


def test_capability_is_canonical_for_inspect_system():
    result = evaluated(
        tool_name="inspect_system",
    )

    assert (
        result.capability
        == "system_inspection"
    )


def test_capability_is_canonical_for_execute_command():
    result = evaluated(
        tool_name="execute_command",
        arguments={
            "command": "echo hello",
        },
    )

    assert result.capability == "terminal"


def test_candidate_tool_matches_model_proposal():
    result = evaluated(
        tool_name="inspect_system",
    )

    assert (
        result.candidate.tool_name
        == "inspect_system"
    )


def test_candidate_capability_matches_evaluation():
    result = evaluated()

    assert (
        result.candidate.option.capability
        == result.capability
    )


def test_candidate_simulation_is_not_verified_reality():
    result = evaluated()

    assert (
        result.candidate.simulation.outcome_verified
        is False
    )


def test_shadow_result_does_not_retain_raw_arguments():
    result = evaluated(
        arguments={
            "secret_value": "do-not-retain-raw",
        },
    )

    assert not hasattr(
        result,
        "arguments",
    )

    assert (
        "do-not-retain-raw"
        not in repr(
            result
        )
    )


def test_arguments_digest_is_sha256():
    result = evaluated(
        arguments={
            "a": 1,
        },
    )

    assert len(
        result.arguments_digest
    ) == 64

    assert all(
        character
        in "0123456789abcdef"
        for character
        in result.arguments_digest
    )


def test_argument_order_does_not_change_digest():
    first = arguments_digest(
        {
            "a": 1,
            "b": 2,
        }
    )

    second = arguments_digest(
        {
            "b": 2,
            "a": 1,
        }
    )

    assert first == second


def test_nested_argument_order_does_not_change_digest():
    first = arguments_digest(
        {
            "outer": {
                "a": 1,
                "b": 2,
            }
        }
    )

    second = arguments_digest(
        {
            "outer": {
                "b": 2,
                "a": 1,
            }
        }
    )

    assert first == second


def test_different_arguments_change_digest():
    assert (
        arguments_digest(
            {"a": 1}
        )
        != arguments_digest(
            {"a": 2}
        )
    )


def test_tuple_and_list_are_canonicalized_consistently():
    assert (
        arguments_digest(
            {"items": (1, 2)}
        )
        == arguments_digest(
            {"items": [1, 2]}
        )
    )


def test_arguments_must_be_mapping():
    with pytest.raises(
        TypeError,
        match="mapping",
    ):
        arguments_digest(
            ["not", "mapping"]
        )


def test_nonstring_mapping_key_fails_closed():
    with pytest.raises(
        TypeError,
        match="string keys",
    ):
        arguments_digest(
            {
                1: "value",
            }
        )


def test_nonfinite_float_fails_closed():
    with pytest.raises(
        ValueError,
        match="non-finite",
    ):
        arguments_digest(
            {
                "value": float("inf"),
            }
        )


def test_unsupported_argument_type_fails_closed():
    with pytest.raises(
        TypeError,
        match="unsupported",
    ):
        arguments_digest(
            {
                "value": object(),
            }
        )


def test_argument_depth_is_bounded():
    value = {}
    current = value

    for index in range(20):
        nested = {}
        current[
            f"level_{index}"
        ] = nested
        current = nested

    with pytest.raises(
        ValueError,
        match="nesting",
    ):
        arguments_digest(
            value
        )


def test_argument_item_count_is_bounded():
    with pytest.raises(
        ValueError,
        match="item count",
    ):
        arguments_digest(
            {
                str(index): index
                for index
                in range(600)
            }
        )


def test_missing_runtime_tool_returns_unavailable():
    result = evaluate_shadow_action(
        situation=make_situation(),
        tool_name="inspect_system",
        arguments={},
        available_tool_names=(),
    )

    assert (
        result.status
        == ShadowActionStatus.UNAVAILABLE
    )
    assert result.candidate is None
    assert result.decision is None
    assert result.authority == "NONE"


def test_registered_tool_without_capability_returns_unavailable():
    result = evaluate_shadow_action(
        situation=make_situation(),
        tool_name="made_up_runtime_tool",
        arguments={},
        available_tool_names=(
            "made_up_runtime_tool",
        ),
    )

    assert (
        result.status
        == ShadowActionStatus.UNAVAILABLE
    )
    assert result.capability is None
    assert result.candidate is None
    assert result.decision is None


def test_unavailable_result_still_carries_arguments_digest():
    result = evaluate_shadow_action(
        situation=make_situation(),
        tool_name="made_up_runtime_tool",
        arguments={
            "a": 1,
        },
        available_tool_names=(
            "made_up_runtime_tool",
        ),
    )

    assert len(
        result.arguments_digest
    ) == 64


def test_tool_name_must_be_string():
    with pytest.raises(
        TypeError,
        match="tool_name",
    ):
        evaluate_shadow_action(
            situation=make_situation(),
            tool_name=1,
            arguments={},
            available_tool_names=(),
        )


def test_tool_name_cannot_be_blank():
    with pytest.raises(
        ValueError,
        match="blank",
    ):
        evaluate_shadow_action(
            situation=make_situation(),
            tool_name=" ",
            arguments={},
            available_tool_names=(),
        )


def test_available_tool_names_must_not_be_single_string():
    with pytest.raises(
        TypeError,
        match="iterable",
    ):
        evaluate_shadow_action(
            situation=make_situation(),
            tool_name="inspect_system",
            arguments={},
            available_tool_names="inspect_system",
        )


def test_available_tool_names_are_order_independent():
    first = evaluate_shadow_action(
        situation=make_situation(),
        tool_name="inspect_system",
        arguments={},
        available_tool_names=(
            "inspect_system",
            "execute_command",
        ),
    )

    second = evaluate_shadow_action(
        situation=make_situation(),
        tool_name="inspect_system",
        arguments={},
        available_tool_names=(
            "execute_command",
            "inspect_system",
        ),
    )

    assert first.capability == second.capability
    assert (
        first.arguments_digest
        == second.arguments_digest
    )


def test_available_tool_names_are_bounded():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        evaluate_shadow_action(
            situation=make_situation(),
            tool_name="inspect_system",
            arguments={},
            available_tool_names=tuple(
                f"tool_{index}"
                for index
                in range(129)
            ),
        )


def test_situation_must_be_tactical_situation():
    with pytest.raises(
        TypeError,
        match="TacticalSituation",
    ):
        evaluate_shadow_action(
            situation=object(),
            tool_name="inspect_system",
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
        )


def test_tampered_situation_authority_fails_closed():
    situation = make_situation()
    object.__setattr__(
        situation,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(
        ValueError,
        match="authority",
    ):
        evaluate_shadow_action(
            situation=situation,
            tool_name="inspect_system",
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
        )


def test_result_has_no_permission_surface():
    result = evaluated()

    assert not hasattr(
        result,
        "permission",
    )
    assert not hasattr(
        result,
        "approved",
    )
    assert not hasattr(
        result,
        "authorized",
    )


def test_result_has_no_execution_surface():
    result = evaluated()

    for name in (
        "execute",
        "executor",
        "execution_result",
        "verified",
        "success",
        "handoff",
        "confirmation",
    ):
        assert not hasattr(
            result,
            name,
        )


def test_evaluator_signature_is_narrow_and_keyword_only():
    signature = inspect.signature(
        evaluate_shadow_action
    )

    assert tuple(
        signature.parameters
    ) == (
        "situation",
        "tool_name",
        "arguments",
        "available_tool_names",
    )

    for parameter in (
        signature.parameters.values()
    ):
        assert (
            parameter.kind
            == inspect.Parameter.KEYWORD_ONLY
        )


def test_module_does_not_import_executor():
    assert (
        "app.agent.executor"
        not in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_execution_bridge():
    assert (
        "app.agent.tactical_execution_bridge"
        not in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_kuma_agent():
    assert (
        "app.agent.kuma_agent"
        not in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_realtime_runtime():
    assert (
        "app.realtime.runtime"
        not in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_ui_observation():
    assert all(
        not name.startswith(
            "app.ui_observation"
        )
        for name
        in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_memory():
    assert all(
        not name.startswith(
            "app.memory"
        )
        for name
        in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_network_clients():
    imports = imports_for(
        MODULE
    )

    assert "requests" not in imports
    assert "urllib" not in imports


def test_module_does_not_import_subprocess_threading_asyncio():
    imports = imports_for(
        MODULE
    )

    assert "subprocess" not in imports
    assert "threading" not in imports
    assert "asyncio" not in imports


def test_module_has_no_while_loop():
    tree = ast.parse(
        module_source()
    )

    assert not any(
        isinstance(
            node,
            ast.While,
        )
        for node
        in ast.walk(
            tree
        )
    )


def test_module_never_calls_execute():
    assert (
        "execute"
        not in calls_for(
            MODULE
        )
    )


def test_module_never_calls_confirmation():
    calls = calls_for(
        MODULE
    )

    assert (
        "request_confirmation"
        not in calls
    )
    assert (
        "confirmation_callback"
        not in calls
    )


def test_module_never_registers_tools():
    assert (
        "register_tool"
        not in calls_for(
            MODULE
        )
    )


def test_module_never_calls_model():
    calls = calls_for(
        MODULE
    )

    assert "ask_model" not in calls
    assert "generate_content" not in calls


def test_module_never_polls_realtime():
    calls = calls_for(
        MODULE
    )

    for name in (
        "pending_signals",
        "drain_signals",
        "refresh_weather",
        "refresh_weather_daily",
    ):
        assert name not in calls


def test_module_never_captures_desktop():
    calls = calls_for(
        MODULE
    )

    for name in (
        "screenshot_screen",
        "analyze_screen",
        "collect_structured_ui",
    ):
        assert name not in calls


def test_module_never_writes_persistence():
    calls = calls_for(
        MODULE
    )

    for name in (
        "open",
        "write_text",
        "write_bytes",
        "connect",
        "commit",
    ):
        assert name not in calls


def test_agent_initializes_shadow_result_before_1a_try():
    text = agent_source()

    marker = (
        "# KUMA-INTEGRATION-1A — RAPHAEL SHADOW COGNITION"
    )

    start = text.index(
        marker
    )

    end = text.index(
        "# BUILD BOUNDED CONTEXT",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "shadow_result = None"
        in block
    )

    assert (
        block.index(
            "shadow_result = None"
        )
        < block.index(
            "try:"
        )
    )


def test_agent_calls_shadow_action_exactly_once():
    assert (
        agent_source().count(
            "evaluate_shadow_action("
        )
        == 1
    )


def test_1b_hook_is_after_argument_validation():
    text = agent_source()

    validation = text.index(
        "arguments_valid, argument_error = ("
    )

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    assert validation < shadow


def test_1b_hook_is_after_invalid_argument_return():
    text = agent_source()

    invalid = text.index(
        "if not arguments_valid:"
    )

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    assert invalid < shadow


def test_1b_hook_is_after_current_request_grounding_gate():
    text = agent_source()

    grounding = text.index(
        "# CURRENT-REQUEST TOOL INTENT GATE"
    )

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    assert grounding < shadow


def test_1b_hook_is_after_dangerous_current_request_gate():
    text = agent_source()

    safety = text.index(
        "# CURRENT-REQUEST SAFETY GATE"
    )

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    assert safety < shadow


def test_1b_hook_is_after_unknown_tool_guard():
    text = agent_source()

    unknown = text.index(
        "# UNKNOWN TOOL GUARD"
    )

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    assert unknown < shadow


def test_1b_hook_is_before_build_action():
    text = agent_source()

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    build = text.index(
        "# BUILD ACTION",
        shadow,
    )

    assert shadow < build


def test_1b_hook_is_before_permission():
    text = agent_source()

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    permission = text.index(
        "# PERMISSION",
        shadow,
    )

    assert shadow < permission


def test_1b_hook_is_before_confirmation_call():
    text = agent_source()

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    confirmation = text.index(
        "self.request_confirmation(",
        shadow,
    )

    assert shadow < confirmation


def test_1b_hook_is_before_executor_call():
    text = agent_source()

    shadow = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    execute = text.index(
        "self.executor.execute(",
        shadow,
    )

    assert shadow < execute


def test_1b_hook_uses_existing_1a_situation():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "situation=shadow_result.situation"
        in block
    )


def test_1b_hook_passes_normalized_tool_name():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "tool_name=tool_name" in block


def test_1b_hook_passes_normalized_arguments():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "arguments=arguments" in block


def test_1b_hook_passes_registered_tool_names_only():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "self.tool_registry.keys()"
        in block
    )
    assert (
        "self.tool_registry.values()"
        not in block
    )


def test_1b_hook_is_exception_isolated():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "try:" in block
    assert (
        "except Exception as error:"
        in block
    )


def test_1b_hook_has_no_return_or_continue():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "return " not in block
    assert "continue" not in block


def test_1b_hook_does_not_call_executor():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "self.executor" not in block


def test_1b_hook_does_not_request_confirmation():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "request_confirmation"
        not in block
    )


def test_1b_hook_does_not_set_approved():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "approved =" not in block


def test_1b_hook_does_not_emit_user_status():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "emit_status(" not in block


def test_1b_hook_does_not_append_model_messages():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "messages.append" not in block
    assert "messages.insert" not in block


def test_1b_hook_does_not_store_result_on_agent():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "self.shadow_action" not in block
    assert "self._raphael" not in block


def test_1b_hook_log_does_not_print_raw_arguments():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert 'f"{arguments}"' not in block
    assert "print(arguments)" not in block


def test_1b_hook_explicitly_declares_no_authority():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "AUTHORITY:NONE" in block
    assert "SHADOW DECISION != AUTHORITY" in block


def test_evaluated_decision_is_tactical_decision_not_authority():
    result = evaluated()

    assert isinstance(
        result.decision.disposition,
        TacticalDisposition,
    )
    assert result.decision.authority == "NONE"
    assert result.authority == "NONE"


def test_dangerous_candidate_does_not_create_confirmation_state():
    result = evaluated(
        tool_name="execute_command",
        arguments={
            "command": "echo hello",
        },
    )

    assert not hasattr(
        result,
        "confirmation",
    )
    assert not hasattr(
        result,
        "approved",
    )
    assert result.authority == "NONE"


def test_same_proposal_is_deterministic():
    first = evaluated(
        tool_name="inspect_system",
        arguments={},
    )
    second = evaluated(
        tool_name="inspect_system",
        arguments={},
    )

    assert (
        first.arguments_digest
        == second.arguments_digest
    )
    assert (
        first.candidate.option.option_id
        == second.candidate.option.option_id
    )
    assert (
        first.decision
        == second.decision
    )


def test_different_arguments_change_shadow_option_identity():
    first = evaluated(
        tool_name="execute_command",
        arguments={
            "command": "echo one",
        },
    )

    second = evaluated(
        tool_name="execute_command",
        arguments={
            "command": "echo two",
        },
    )

    assert (
        first.candidate.option.option_id
        != second.candidate.option.option_id
    )


def test_evaluator_does_not_mutate_arguments():
    arguments = {
        "command": "echo hello",
    }

    before = dict(
        arguments
    )

    evaluated(
        tool_name="execute_command",
        arguments=arguments,
    )

    assert arguments == before


def test_evaluator_does_not_mutate_situation():
    situation = make_situation()
    before = repr(
        situation
    )

    evaluate_shadow_action(
        situation=situation,
        tool_name="inspect_system",
        arguments={},
        available_tool_names=(
            "inspect_system",
        ),
    )

    assert repr(
        situation
    ) == before
