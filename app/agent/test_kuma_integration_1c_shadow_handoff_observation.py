from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import inspect
from pathlib import Path

import pytest

from app.agent.cognitive_contracts import (
    TacticalSituation,
    WorldStateSnapshot,
)
from app.agent.shadow_action_evaluation import (
    ShadowActionStatus,
    evaluate_shadow_action,
)
import app.agent.shadow_handoff_observation as shadow_handoff_module

from app.agent.shadow_handoff_observation import (
    ShadowHandoffObservation,
    ShadowHandoffStatus,
    observe_shadow_handoff,
)
from app.agent.tactical_execution_bridge import (
    HandoffAssessment,
    HandoffDisposition,
)


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "app/agent/kuma_agent.py"
MODULE = ROOT / "app/agent/shadow_handoff_observation.py"

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
        available_capabilities=(
            "system_inspection",
            "terminal",
            "mouse_control",
        ),
        world_state=snapshot,
    )


def make_evaluation(
    *,
    situation=None,
    tool_name="inspect_system",
    arguments=None,
    available_tool_names=None,
):
    if situation is None:
        situation = make_situation()

    if arguments is None:
        arguments = {}

    if available_tool_names is None:
        available_tool_names = (
            "inspect_system",
            "execute_command",
            "click",
        )

    return evaluate_shadow_action(
        situation=situation,
        tool_name=tool_name,
        arguments=arguments,
        available_tool_names=available_tool_names,
    )


def observe(
    *,
    situation=None,
    action_evaluation=None,
    current_request="inspect the system",
    arguments=None,
    available_tool_names=None,
    current_request_grounded=True,
):
    if situation is None:
        situation = make_situation()

    if arguments is None:
        arguments = {}

    if available_tool_names is None:
        available_tool_names = (
            "inspect_system",
            "execute_command",
            "click",
        )

    if action_evaluation is None:
        action_evaluation = make_evaluation(
            situation=situation,
            arguments=arguments,
            available_tool_names=available_tool_names,
        )

    return observe_shadow_handoff(
        situation=situation,
        action_evaluation=action_evaluation,
        current_request=current_request,
        arguments=arguments,
        available_tool_names=available_tool_names,
        current_request_grounded=current_request_grounded,
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
                result.add(
                    node.module
                )

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


def test_status_surface_is_exact():
    assert {
        item.name
        for item in ShadowHandoffStatus
    } == {
        "ASSESSED",
        "SKIPPED",
    }


def test_observation_is_frozen():
    result = observe()

    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"


def test_observation_authority_is_none():
    result = observe()

    assert result.authority == "NONE"


def test_real_bridge_assessment_authority_is_none():
    result = observe()

    assert result.assessment is not None
    assert result.assessment.authority == "NONE"


def test_real_1b_advise_decision_is_rejected_by_frozen_bridge():
    evaluation = make_evaluation(
        tool_name="inspect_system",
    )

    assert (
        evaluation.decision.disposition.value
        == "advise"
    )

    result = observe(
        action_evaluation=evaluation,
    )

    assert (
        result.status
        == ShadowHandoffStatus.ASSESSED
    )
    assert (
        result.assessment.disposition
        == HandoffDisposition.REJECTED
    )
    assert result.authority == "NONE"


def test_rejected_bridge_assessment_does_not_become_local_rejection_status():
    result = observe()

    assert (
        result.status
        == ShadowHandoffStatus.ASSESSED
    )
    assert (
        result.assessment.disposition
        == HandoffDisposition.REJECTED
    )


def test_false_grounding_still_returns_zero_authority_assessment():
    result = observe(
        current_request_grounded=False,
    )

    assert (
        result.status
        == ShadowHandoffStatus.ASSESSED
    )
    assert (
        result.assessment.disposition
        == HandoffDisposition.REJECTED
    )
    assert result.authority == "NONE"


def test_argument_digest_mismatch_skips_bridge():
    situation = make_situation()

    evaluation = make_evaluation(
        situation=situation,
        arguments={
            "a": 1,
        },
    )

    result = observe_shadow_handoff(
        situation=situation,
        action_evaluation=evaluation,
        current_request="inspect the system",
        arguments={
            "a": 2,
        },
        available_tool_names=(
            "inspect_system",
        ),
        current_request_grounded=True,
    )

    assert (
        result.status
        == ShadowHandoffStatus.SKIPPED
    )
    assert result.assessment is None
    assert result.authority == "NONE"


def test_unavailable_1b_evaluation_skips_bridge():
    situation = make_situation()

    evaluation = make_evaluation(
        situation=situation,
        tool_name="unknown_runtime_tool",
        available_tool_names=(
            "unknown_runtime_tool",
        ),
    )

    assert (
        evaluation.status
        == ShadowActionStatus.UNAVAILABLE
    )

    result = observe_shadow_handoff(
        situation=situation,
        action_evaluation=evaluation,
        current_request="use the unknown tool",
        arguments={},
        available_tool_names=(
            "unknown_runtime_tool",
        ),
        current_request_grounded=True,
    )

    assert (
        result.status
        == ShadowHandoffStatus.SKIPPED
    )
    assert result.assessment is None


def test_skipped_observation_cannot_carry_assessment():
    with pytest.raises(
        ValueError,
        match="SKIPPED",
    ):
        ShadowHandoffObservation(
            status=ShadowHandoffStatus.SKIPPED,
            tool_name="inspect_system",
            arguments_digest="0" * 64,
            reason="skip",
            assessment=HandoffAssessment(
                disposition=HandoffDisposition.REJECTED,
                reason="reject",
            ),
        )


def test_assessed_observation_requires_assessment():
    with pytest.raises(
        ValueError,
        match="ASSESSED",
    ):
        ShadowHandoffObservation(
            status=ShadowHandoffStatus.ASSESSED,
            tool_name="inspect_system",
            arguments_digest="0" * 64,
            reason="assessed",
        )


def test_invalid_digest_fails_closed():
    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        ShadowHandoffObservation(
            status=ShadowHandoffStatus.SKIPPED,
            tool_name="inspect_system",
            arguments_digest="bad",
            reason="skip",
        )


def test_blank_tool_name_fails_closed():
    with pytest.raises(
        ValueError,
        match="tool_name",
    ):
        ShadowHandoffObservation(
            status=ShadowHandoffStatus.SKIPPED,
            tool_name=" ",
            arguments_digest="0" * 64,
            reason="skip",
        )


def test_blank_reason_fails_closed():
    with pytest.raises(
        ValueError,
        match="reason",
    ):
        ShadowHandoffObservation(
            status=ShadowHandoffStatus.SKIPPED,
            tool_name="inspect_system",
            arguments_digest="0" * 64,
            reason=" ",
        )


def test_current_request_must_be_string():
    with pytest.raises(
        TypeError,
        match="current_request",
    ):
        observe_shadow_handoff(
            situation=make_situation(),
            action_evaluation=make_evaluation(),
            current_request=None,
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
            current_request_grounded=True,
        )


def test_current_request_cannot_be_blank():
    with pytest.raises(
        ValueError,
        match="blank",
    ):
        observe_shadow_handoff(
            situation=make_situation(),
            action_evaluation=make_evaluation(),
            current_request=" ",
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
            current_request_grounded=True,
        )


def test_grounding_result_must_be_bool():
    with pytest.raises(
        TypeError,
        match="bool",
    ):
        observe_shadow_handoff(
            situation=make_situation(),
            action_evaluation=make_evaluation(),
            current_request="inspect the system",
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
            current_request_grounded=1,
        )


def test_situation_must_be_tactical_situation():
    with pytest.raises(
        TypeError,
        match="TacticalSituation",
    ):
        observe_shadow_handoff(
            situation=object(),
            action_evaluation=make_evaluation(),
            current_request="inspect the system",
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
            current_request_grounded=True,
        )


def test_action_evaluation_must_be_correct_type():
    with pytest.raises(
        TypeError,
        match="ShadowActionEvaluation",
    ):
        observe_shadow_handoff(
            situation=make_situation(),
            action_evaluation=object(),
            current_request="inspect the system",
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
            current_request_grounded=True,
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
        observe_shadow_handoff(
            situation=situation,
            action_evaluation=make_evaluation(),
            current_request="inspect the system",
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
            current_request_grounded=True,
        )


def test_tampered_action_evaluation_authority_fails_closed():
    evaluation = make_evaluation()

    object.__setattr__(
        evaluation,
        "authority",
        "AUTHORIZED",
    )

    with pytest.raises(
        ValueError,
        match="authority",
    ):
        observe_shadow_handoff(
            situation=make_situation(),
            action_evaluation=evaluation,
            current_request="inspect the system",
            arguments={},
            available_tool_names=(
                "inspect_system",
            ),
            current_request_grounded=True,
        )


def test_request_whitespace_is_normalized_before_bridge():
    first = observe(
        current_request="inspect the system",
    )

    second = observe(
        current_request="   inspect the system   ",
    )

    assert (
        first.assessment.disposition
        == second.assessment.disposition
    )


def test_observation_has_no_approval_surface():
    result = observe()

    for name in (
        "approved",
        "permission_granted",
        "authorized",
        "confirmation",
    ):
        assert not hasattr(
            result,
            name,
        )


def test_observation_has_no_execution_surface():
    result = observe()

    for name in (
        "execute",
        "executor",
        "execution_result",
        "success",
        "verified",
    ):
        assert not hasattr(
            result,
            name,
        )


def test_observation_does_not_expose_raw_arguments_directly():
    result = observe(
        arguments={
            "secret": "value",
        },
        action_evaluation=make_evaluation(
            arguments={
                "secret": "value",
            },
        ),
    )

    assert not hasattr(
        result,
        "arguments",
    )


def test_observer_signature_is_narrow_and_keyword_only():
    signature = inspect.signature(
        observe_shadow_handoff
    )

    assert tuple(
        signature.parameters
    ) == (
        "situation",
        "action_evaluation",
        "current_request",
        "arguments",
        "available_tool_names",
        "current_request_grounded",
    )

    for parameter in (
        signature.parameters.values()
    ):
        assert (
            parameter.kind
            == inspect.Parameter.KEYWORD_ONLY
        )


def test_module_imports_frozen_execution_bridge():
    assert (
        "app.agent.tactical_execution_bridge"
        in imports_for(
            MODULE
        )
    )


def test_module_imports_integration_1b_evaluation():
    assert (
        "app.agent.shadow_action_evaluation"
        in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_executor():
    assert (
        "app.agent.executor"
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


def test_module_never_calls_executor_execute():
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


def test_module_never_calls_model():
    calls = calls_for(
        MODULE
    )

    assert "ask_model" not in calls
    assert "generate_content" not in calls


def test_module_never_registers_tools():
    assert (
        "register_tool"
        not in calls_for(
            MODULE
        )
    )


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


def test_agent_initializes_1b_result_before_1b_try():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    end = text.index(
        "# KUMA-INTEGRATION-1C",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "shadow_action_evaluation = None"
        in block
    )

    assert (
        block.index(
            "shadow_action_evaluation = None"
        )
        < block.index(
            "try:"
        )
    )


def test_agent_calls_handoff_observer_exactly_once():
    assert (
        agent_source().count(
            "observe_shadow_handoff("
        )
        == 1
    )


def test_1c_hook_is_after_1b_hook():
    text = agent_source()

    one_b = text.index(
        "# KUMA-INTEGRATION-1B"
    )

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    assert one_b < one_c


def test_1c_hook_is_after_argument_validation():
    text = agent_source()

    validation = text.index(
        "arguments_valid, argument_error = ("
    )

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    assert validation < one_c


def test_1c_hook_is_before_build_action():
    text = agent_source()

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    build = text.index(
        "# BUILD ACTION",
        one_c,
    )

    assert one_c < build


def test_1c_hook_is_before_permission():
    text = agent_source()

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    permission = text.index(
        "# PERMISSION",
        one_c,
    )

    assert one_c < permission


def test_1c_hook_is_before_confirmation():
    text = agent_source()

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    confirmation = text.index(
        "self.request_confirmation(",
        one_c,
    )

    assert one_c < confirmation


def test_1c_hook_is_before_executor():
    text = agent_source()

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    execute = text.index(
        "self.executor.execute(",
        one_c,
    )

    assert one_c < execute


def test_1c_hook_uses_1a_situation():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
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


def test_1c_hook_uses_1b_action_evaluation():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "action_evaluation=shadow_action_evaluation"
        in block
    )


def test_1c_hook_passes_exact_current_request():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "current_request=user_message"
        in block
    )


def test_1c_hook_passes_normalized_arguments():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "arguments=arguments" in block


def test_1c_hook_passes_registered_tool_names():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
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


def test_1c_hook_uses_existing_grounding_results():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "explicitly_grounded" in block
    assert "clarification_grounded" in block
    assert (
        "current_request_grounded="
        in block
    )


def test_1c_hook_does_not_reinvoke_grounding_methods():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "explicitly_requests_tool_action("
        not in block
    )
    assert (
        "_consume_grounded_web_continuation("
        not in block
    )


def test_1c_hook_is_exception_isolated():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
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


def test_1c_hook_has_no_return_or_continue():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "return " not in block
    assert "\n                continue" not in block
    assert "\n            continue" not in block


def test_1c_hook_does_not_call_executor():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "self.executor" not in block


def test_1c_hook_does_not_request_confirmation():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "request_confirmation("
        not in block
    )


def test_1c_hook_does_not_set_approved():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "approved =" not in block


def test_1c_hook_does_not_assign_permission():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "\n            permission =" not in block


def test_1c_hook_does_not_mutate_model_messages():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
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


def test_1c_hook_does_not_emit_user_status():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "emit_status(" not in block


def test_1c_hook_does_not_store_observation_on_agent():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "self.shadow_handoff" not in block
    assert "self._raphael" not in block


def test_1c_hook_does_not_branch_on_handoff_disposition():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert (
        "== HandoffDisposition"
        not in block
    )
    assert (
        "!= HandoffDisposition"
        not in block
    )


def test_1c_hook_does_not_use_handoff_arguments_for_live_action():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert ".handoff.arguments" not in block
    assert "arguments_copy" not in block


def test_1c_hook_explicitly_declares_zero_authority_boundaries():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    block = text[
        start:end
    ]

    assert "HANDOFF != APPROVAL" in block
    assert "FORWARD_TO_KUMA != PERMISSION" in block
    assert "AUTHORITY:NONE" in block


def test_existing_build_action_still_uses_original_tool_and_arguments():
    text = agent_source()

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    start = text.index(
        "# BUILD ACTION",
        one_c,
    )

    window = text[
        start:start + 350
    ]

    assert (
        "self.build_action("
        in window
    )
    assert "tool_name" in window
    assert "arguments" in window
    assert "shadow_handoff" not in window


def test_existing_permission_still_uses_tool_name():
    text = agent_source()

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    start = text.index(
        "# PERMISSION",
        one_c,
    )

    window = text[
        start:start + 500
    ]

    assert (
        "get_permission_level("
        in window
    )
    assert "tool_name" in window
    assert "shadow_handoff" not in window


def test_existing_executor_still_uses_live_tool_name_and_arguments():
    text = agent_source()

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    start = text.index(
        "self.executor.execute(",
        one_c,
    )

    window = text[
        start:start + 300
    ]

    assert "tool_name=tool_name" in window
    assert "arguments=arguments" in window
    assert "approved=approved" in window
    assert "shadow_handoff" not in window

def test_bound_authorizer_replays_existing_true_grounding_exactly(monkeypatch):
    captured = {}

    class RecordingBridge:
        def __init__(
            self,
            *,
            capability_registry,
            current_request_authorizer,
        ):
            captured["authorizer"] = current_request_authorizer

        def prepare(
            self,
            *,
            situation,
            decision,
            candidate,
            current_request,
            arguments,
            available_tool_names,
        ):
            captured["exact"] = captured["authorizer"](
                current_request,
                candidate.tool_name,
                dict(arguments),
            )

            return HandoffAssessment(
                disposition=HandoffDisposition.REJECTED,
                reason="recording bridge",
            )

    monkeypatch.setattr(
        shadow_handoff_module,
        "RaphaelExecutionBridge",
        RecordingBridge,
    )

    result = observe(
        current_request_grounded=True,
    )

    assert captured["exact"] is True
    assert result.authority == "NONE"


def test_bound_authorizer_replays_existing_false_grounding_exactly(monkeypatch):
    captured = {}

    class RecordingBridge:
        def __init__(
            self,
            *,
            capability_registry,
            current_request_authorizer,
        ):
            captured["authorizer"] = current_request_authorizer

        def prepare(
            self,
            *,
            situation,
            decision,
            candidate,
            current_request,
            arguments,
            available_tool_names,
        ):
            captured["exact"] = captured["authorizer"](
                current_request,
                candidate.tool_name,
                dict(arguments),
            )

            return HandoffAssessment(
                disposition=HandoffDisposition.REJECTED,
                reason="recording bridge",
            )

    monkeypatch.setattr(
        shadow_handoff_module,
        "RaphaelExecutionBridge",
        RecordingBridge,
    )

    observe(
        current_request_grounded=False,
    )

    assert captured["exact"] is False


def test_bound_authorizer_rejects_changed_tool_identity(monkeypatch):
    captured = {}

    class RecordingBridge:
        def __init__(
            self,
            *,
            capability_registry,
            current_request_authorizer,
        ):
            captured["authorizer"] = current_request_authorizer

        def prepare(
            self,
            *,
            situation,
            decision,
            candidate,
            current_request,
            arguments,
            available_tool_names,
        ):
            captured["changed_tool"] = captured["authorizer"](
                current_request,
                "execute_command",
                dict(arguments),
            )

            return HandoffAssessment(
                disposition=HandoffDisposition.REJECTED,
                reason="recording bridge",
            )

    monkeypatch.setattr(
        shadow_handoff_module,
        "RaphaelExecutionBridge",
        RecordingBridge,
    )

    observe(
        current_request_grounded=True,
    )

    assert captured["changed_tool"] is False


def test_bound_authorizer_rejects_changed_arguments(monkeypatch):
    captured = {}

    class RecordingBridge:
        def __init__(
            self,
            *,
            capability_registry,
            current_request_authorizer,
        ):
            captured["authorizer"] = current_request_authorizer

        def prepare(
            self,
            *,
            situation,
            decision,
            candidate,
            current_request,
            arguments,
            available_tool_names,
        ):
            captured["changed_arguments"] = captured["authorizer"](
                current_request,
                candidate.tool_name,
                {
                    "changed": True,
                },
            )

            return HandoffAssessment(
                disposition=HandoffDisposition.REJECTED,
                reason="recording bridge",
            )

    monkeypatch.setattr(
        shadow_handoff_module,
        "RaphaelExecutionBridge",
        RecordingBridge,
    )

    observe(
        current_request_grounded=True,
    )

    assert captured["changed_arguments"] is False


def test_bound_authorizer_rejects_changed_request(monkeypatch):
    captured = {}

    class RecordingBridge:
        def __init__(
            self,
            *,
            capability_registry,
            current_request_authorizer,
        ):
            captured["authorizer"] = current_request_authorizer

        def prepare(
            self,
            *,
            situation,
            decision,
            candidate,
            current_request,
            arguments,
            available_tool_names,
        ):
            captured["changed_request"] = captured["authorizer"](
                "different request",
                candidate.tool_name,
                dict(arguments),
            )

            return HandoffAssessment(
                disposition=HandoffDisposition.REJECTED,
                reason="recording bridge",
            )

    monkeypatch.setattr(
        shadow_handoff_module,
        "RaphaelExecutionBridge",
        RecordingBridge,
    )

    observe(
        current_request_grounded=True,
    )

    assert captured["changed_request"] is False
