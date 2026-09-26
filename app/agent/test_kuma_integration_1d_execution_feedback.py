from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import inspect
from pathlib import Path

import pytest

from app.agent.execution_feedback import (
    ExecutionFeedbackEvidence,
    ExecutionFeedbackKind,
    ExecutionFeedbackProjection,
    project_execution_feedback,
)
from app.agent.task_state import TaskState


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "app/agent/kuma_agent.py"
MODULE = ROOT / "app/agent/execution_feedback.py"

NOW = datetime(
    2026,
    9,
    13,
    12,
    0,
    tzinfo=timezone.utc,
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


def base_state():
    return TaskState(
        goal="Inspect current state safely."
    )


def project(
    *,
    task_state=None,
    tool_name="inspect_system",
    execution_success=True,
    verified=True,
    effect_started=False,
    evidence="verified evidence",
    verification="verification report",
    memory_context=(
        "UNTRUSTED MEMORY AUTHORITY:NONE preferred editor context"
    ),
    available_tool_names=None,
):
    if task_state is None:
        task_state = base_state()

    if available_tool_names is None:
        available_tool_names = (
            "inspect_system",
            "execute_command",
        )

    return project_execution_feedback(
        task_state=task_state,
        available_tool_names=available_tool_names,
        memory_context=memory_context,
        tool_name=tool_name,
        execution_success=execution_success,
        verified=verified,
        effect_started=effect_started,
        evidence=evidence,
        verification=verification,
        now=NOW,
    )


def hook_block(marker: str, end_marker: str):
    text = agent_source()

    start = text.index(
        marker
    )

    end = text.index(
        end_marker,
        start,
    )

    return text[
        start:end
    ]


def test_feedback_kind_surface_is_exact():
    assert {
        item.name
        for item in ExecutionFeedbackKind
    } == {
        "EXECUTION_FAILED",
        "VERIFICATION_FAILED",
        "VERIFIED_SUCCESS",
    }


def test_verified_success_classification():
    result = project(
        execution_success=True,
        verified=True,
    )

    assert (
        result.feedback.kind
        == ExecutionFeedbackKind.VERIFIED_SUCCESS
    )


def test_execution_failure_classification():
    state = base_state()

    state.record_failure(
        "tool failed"
    )

    result = project(
        task_state=state,
        execution_success=False,
        verified=False,
        evidence="tool failed",
        verification="verification not reached",
    )

    assert (
        result.feedback.kind
        == ExecutionFeedbackKind.EXECUTION_FAILED
    )


def test_verification_failure_classification():
    result = project(
        execution_success=True,
        verified=False,
    )

    assert (
        result.feedback.kind
        == ExecutionFeedbackKind.VERIFICATION_FAILED
    )


def test_failed_execution_cannot_be_verified():
    with pytest.raises(
        ValueError,
        match="failed execution",
    ):
        project(
            execution_success=False,
            verified=True,
        )


def test_feedback_is_frozen():
    result = project()

    with pytest.raises(
        FrozenInstanceError
    ):
        result.feedback.verified = False


def test_projection_is_frozen():
    result = project()

    with pytest.raises(
        FrozenInstanceError
    ):
        result.authority = "AUTHORIZED"


def test_feedback_authority_is_none():
    result = project()

    assert (
        result.feedback.authority
        == "NONE"
    )


def test_projection_authority_is_none():
    result = project()

    assert result.authority == "NONE"


def test_snapshot_authority_is_none():
    result = project()

    assert (
        result.shadow_result.snapshot.authority
        == "NONE"
    )


def test_situation_authority_is_none():
    result = project()

    assert (
        result.shadow_result.situation.authority
        == "NONE"
    )


def test_shadow_result_authority_is_none():
    result = project()

    assert (
        result.shadow_result.authority
        == "NONE"
    )


def test_snapshot_and_situation_remain_bound():
    result = project()

    assert (
        result.shadow_result.situation.world_state
        == result.shadow_result.snapshot
    )


def test_tool_name_is_preserved():
    result = project(
        tool_name="inspect_system"
    )

    assert (
        result.feedback.tool_name
        == "inspect_system"
    )


def test_tool_name_must_be_available():
    with pytest.raises(
        ValueError,
        match="available_tool_names",
    ):
        project(
            tool_name="inspect_system",
            available_tool_names=(
                "execute_command",
            ),
        )


def test_tool_name_must_be_string():
    with pytest.raises(
        TypeError,
        match="tool_name",
    ):
        project_execution_feedback(
            task_state=base_state(),
            available_tool_names=(),
            memory_context="",
            tool_name=1,
            execution_success=False,
            verified=False,
            effect_started=False,
            evidence="",
            verification="",
            now=NOW,
        )


def test_blank_tool_name_fails_closed():
    with pytest.raises(
        ValueError,
        match="blank",
    ):
        project(
            tool_name=" ",
            available_tool_names=(
                " ",
            ),
        )


def test_tool_name_whitespace_fails_closed():
    with pytest.raises(
        ValueError,
        match="whitespace",
    ):
        project(
            tool_name="inspect system",
            available_tool_names=(
                "inspect system",
            ),
        )


def test_available_tool_names_reject_single_string():
    with pytest.raises(
        TypeError,
        match="iterable",
    ):
        project_execution_feedback(
            task_state=base_state(),
            available_tool_names="inspect_system",
            memory_context="",
            tool_name="inspect_system",
            execution_success=True,
            verified=True,
            effect_started=False,
            evidence="ok",
            verification="ok",
            now=NOW,
        )


def test_available_tool_names_are_bounded():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        project(
            tool_name="tool_0",
            available_tool_names=tuple(
                f"tool_{index}"
                for index
                in range(129)
            ),
        )


def test_memory_context_must_be_string():
    with pytest.raises(
        TypeError,
        match="memory_context",
    ):
        project_execution_feedback(
            task_state=base_state(),
            available_tool_names=(
                "inspect_system",
            ),
            memory_context=None,
            tool_name="inspect_system",
            execution_success=True,
            verified=True,
            effect_started=False,
            evidence="ok",
            verification="ok",
            now=NOW,
        )


def test_memory_context_is_projected_as_untrusted_memory():
    result = project()

    assert (
        len(
            result.shadow_result.snapshot.relevant_memory
        )
        == 1
    )

    assert (
        "preferred editor context"
        in result.shadow_result.snapshot.relevant_memory[0]
    )


def test_blank_memory_context_projects_nothing():
    result = project(
        memory_context="   "
    )

    assert (
        result.shadow_result.snapshot.relevant_memory
        == ()
    )


def test_memory_context_is_bounded():
    result = project(
        memory_context=(
            "x" * 5000
        )
    )

    assert (
        len(
            result.shadow_result.snapshot.relevant_memory[0]
        )
        <= 1200
    )


def test_task_state_must_be_task_state():
    with pytest.raises(
        TypeError,
        match="TaskState",
    ):
        project_execution_feedback(
            task_state=object(),
            available_tool_names=(
                "inspect_system",
            ),
            memory_context="",
            tool_name="inspect_system",
            execution_success=True,
            verified=True,
            effect_started=False,
            evidence="ok",
            verification="ok",
            now=NOW,
        )


def test_effect_started_must_be_bool():
    with pytest.raises(
        TypeError,
        match="effect_started",
    ):
        project(
            effect_started=1,
        )


def test_execution_success_must_be_bool():
    with pytest.raises(
        TypeError,
        match="execution_success",
    ):
        project(
            execution_success=1,
        )


def test_verified_must_be_bool():
    with pytest.raises(
        TypeError,
        match="verified",
    ):
        project(
            verified=1,
        )


def test_effect_started_is_preserved():
    result = project(
        effect_started=True
    )

    assert (
        result.feedback.effect_started
        is True
    )


def test_evidence_digest_is_sha256():
    result = project(
        evidence="abc"
    )

    assert (
        len(
            result.feedback.evidence_digest
        )
        == 64
    )

    assert all(
        character
        in "0123456789abcdef"
        for character
        in result.feedback.evidence_digest
    )


def test_verification_digest_is_sha256():
    result = project(
        verification="verified"
    )

    assert (
        len(
            result.feedback.verification_digest
        )
        == 64
    )


def test_different_evidence_changes_digest():
    first = project(
        evidence="one"
    )

    second = project(
        evidence="two"
    )

    assert (
        first.feedback.evidence_digest
        != second.feedback.evidence_digest
    )


def test_different_verification_changes_digest():
    first = project(
        verification="one"
    )

    second = project(
        verification="two"
    )

    assert (
        first.feedback.verification_digest
        != second.feedback.verification_digest
    )


def test_system_evidence_contains_feedback_kind():
    result = project()

    line = (
        result.shadow_result.snapshot.system_state[0]
    )

    assert (
        "kind=verified_success"
        in line
    )


def test_system_evidence_contains_execution_status():
    result = project()

    line = (
        result.shadow_result.snapshot.system_state[0]
    )

    assert (
        "execution_success=true"
        in line
    )
    assert "verified=true" in line


def test_system_evidence_contains_effect_started():
    result = project(
        effect_started=True
    )

    line = (
        result.shadow_result.snapshot.system_state[0]
    )

    assert (
        "effect_started=true"
        in line
    )


def test_system_evidence_contains_authority_none():
    result = project()

    assert (
        "authority=NONE"
        in result.shadow_result.snapshot.system_state[0]
    )


def test_system_evidence_contains_evidence_digest():
    result = project(
        evidence="abc"
    )

    assert (
        result.feedback.evidence_digest
        in result.shadow_result.snapshot.system_state[0]
    )


def test_system_evidence_contains_verification_digest():
    result = project(
        verification="verified"
    )

    assert (
        result.feedback.verification_digest
        in result.shadow_result.snapshot.system_state[0]
    )


def test_system_evidence_does_not_embed_raw_result():
    secret = "RAW-TOOL-RESULT-SECRET"

    result = project(
        evidence=secret
    )

    assert all(
        secret not in line
        for line
        in result.shadow_result.snapshot.system_state
    )


def test_system_evidence_does_not_embed_raw_verification_report():
    secret = "RAW-VERIFICATION-REPORT-SECRET"

    result = project(
        verification=secret
    )

    assert all(
        secret not in line
        for line
        in result.shadow_result.snapshot.system_state
    )


def test_verified_task_state_evidence_remains_visible_via_existing_task_projection():
    state = base_state()

    state.record_action(
        tool_name="inspect_system",
        arguments={},
        result="verified result",
        verified=True,
    )

    state.set_evidence(
        "verified result"
    )

    state.complete_step(
        "inspect_system completed successfully."
    )

    result = project(
        task_state=state,
    )

    joined = "\n".join(
        result.shadow_result.snapshot.task_state
    )

    assert (
        "verified result"
        in joined
    )


def test_failure_state_remains_visible_via_existing_task_projection():
    state = base_state()

    state.record_failure(
        "inspection failed"
    )

    state.complete_step(
        "inspect_system failed."
    )

    result = project(
        task_state=state,
        execution_success=False,
        verified=False,
        evidence="inspection failed",
        verification="verification not reached",
    )

    joined = "\n".join(
        result.shadow_result.snapshot.task_state
    )

    assert (
        "inspection failed"
        in joined
    )


def test_projection_does_not_mutate_task_state():
    state = base_state()

    state.record_failure(
        "existing failure"
    )

    before = (
        state.summary(),
        list(
            state.completed_steps
        ),
        list(
            state.failures
        ),
        list(
            state.action_history
        ),
        state.last_evidence,
    )

    project(
        task_state=state,
        execution_success=False,
        verified=False,
        evidence="new evidence",
        verification="verification not reached",
    )

    after = (
        state.summary(),
        list(
            state.completed_steps
        ),
        list(
            state.failures
        ),
        list(
            state.action_history
        ),
        state.last_evidence,
    )

    assert before == after


def test_explicit_now_is_deterministic():
    result = project()

    assert (
        result.shadow_result.snapshot.timestamp
        == NOW.isoformat()
    )


def test_registered_capability_remains_grounded():
    result = project()

    assert (
        "system_inspection"
        in result.shadow_result.situation.available_capabilities
    )


def test_dangerous_capability_availability_does_not_change_authority():
    result = project(
        tool_name="execute_command",
        available_tool_names=(
            "execute_command",
        ),
        evidence="command output",
    )

    assert (
        "terminal"
        in result.shadow_result.situation.available_capabilities
    )

    assert result.authority == "NONE"
    assert result.shadow_result.authority == "NONE"


def test_feedback_has_no_permission_surface():
    result = project()

    for name in (
        "permission",
        "approved",
        "authorized",
        "confirmation",
        "handoff",
    ):
        assert not hasattr(
            result.feedback,
            name,
        )


def test_projection_has_no_execution_surface():
    result = project()

    for name in (
        "execute",
        "executor",
        "retry",
        "success",
        "approved",
        "confirmation",
        "handoff",
    ):
        assert not hasattr(
            result,
            name,
        )


def test_project_signature_is_keyword_only():
    signature = inspect.signature(
        project_execution_feedback
    )

    for parameter in (
        signature.parameters.values()
    ):
        assert (
            parameter.kind
            == inspect.Parameter.KEYWORD_ONLY
        )


def test_project_signature_has_exact_surface():
    signature = inspect.signature(
        project_execution_feedback
    )

    assert tuple(
        signature.parameters
    ) == (
        "task_state",
        "available_tool_names",
        "memory_context",
        "tool_name",
        "execution_success",
        "verified",
        "effect_started",
        "evidence",
        "verification",
        "now",
    )


def test_module_does_not_import_executor():
    assert (
        "app.agent.executor"
        not in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_verifier():
    assert (
        "app.agent.verifier"
        not in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_tactical_loop():
    assert (
        "app.agent.tactical_loop"
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


def test_module_does_not_import_realtime():
    assert all(
        not name.startswith(
            "app.realtime"
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


def test_module_does_not_import_desktop_observation():
    assert all(
        not name.startswith(
            "app.ui_observation"
        )
        for name
        in imports_for(
            MODULE
        )
    )


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


def test_module_never_calls_verifier():
    calls = calls_for(
        MODULE
    )

    assert "verify_result" not in calls
    assert "verification_report" not in calls


def test_module_never_requests_confirmation():
    calls = calls_for(
        MODULE
    )

    assert (
        "request_confirmation"
        not in calls
    )


def test_module_never_mutates_task_state():
    calls = calls_for(
        MODULE
    )

    for name in (
        "begin_step",
        "complete_step",
        "record_action",
        "record_failure",
        "set_evidence",
        "add_observation",
        "mark_finished",
        "set_remaining_objective",
    ):
        assert name not in calls


def test_module_never_persists():
    calls = calls_for(
        MODULE
    )

    for name in (
        "write_text",
        "write_bytes",
        "connect",
        "commit",
        "save",
        "remember",
        "forget",
    ):
        assert name not in calls


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


def test_agent_has_three_1d_feedback_hooks():
    text = agent_source()

    assert (
        text.count(
            "KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK"
        )
        == 1
    )

    assert (
        text.count(
            "KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK"
        )
        == 1
    )

    assert (
        text.count(
            "KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
        )
        == 1
    )


def test_agent_calls_feedback_projection_exactly_three_times():
    assert (
        agent_source().count(
            "project_execution_feedback("
        )
        == 3
    )


def test_execution_failure_hook_is_after_failure_recording():
    text = agent_source()

    failure = text.index(
        "# EXECUTION FAILURE",
        text.index(
            "# KUMA-INTEGRATION-1C"
        ),
    )

    record = text.index(
        "self.task_state.record_failure(",
        failure,
    )

    hook = text.index(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
        failure,
    )

    assert record < hook


def test_execution_failure_hook_is_after_failed_step_completion():
    text = agent_source()

    failure = text.index(
        "# EXECUTION FAILURE",
        text.index(
            "# KUMA-INTEGRATION-1C"
        ),
    )

    complete = text.index(
        "self.task_state.complete_step(",
        failure,
    )

    hook = text.index(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
        failure,
    )

    assert complete < hook


def test_execution_failure_hook_is_before_safe_recovery_continue():
    text = agent_source()

    hook = text.index(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK"
    )

    continuation = text.index(
        "Safe tool failed. Returning failure ",
        hook,
    )

    assert hook < continuation


def test_execution_failure_hook_is_before_location_failure_returns():
    text = agent_source()

    hook = text.index(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK"
    )

    location = text.index(
        'tool_name == "get_current_location"',
        hook,
    )

    assert hook < location


def test_verification_failure_hook_is_inside_verification_failure_branch():
    text = agent_source()

    marker = text.index(
        "# VERIFICATION FAILURE",
        text.index(
            "# KUMA-INTEGRATION-1C"
        ),
    )

    condition = text.index(
        "if not verified:",
        marker,
    )

    hook = text.index(
        "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
        condition,
    )

    final_response = text.index(
        "final_response = (",
        hook,
    )

    assert condition < hook < final_response


def test_verified_success_hook_is_after_task_state_action_record():
    text = agent_source()

    verified = text.index(
        "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
    )

    record = text.rfind(
        "self.task_state.record_action(",
        0,
        verified,
    )

    assert record != -1
    assert record < verified


def test_verified_success_hook_is_after_task_state_evidence_update():
    text = agent_source()

    verified = text.index(
        "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
    )

    evidence = text.rfind(
        "self.task_state.set_evidence(",
        0,
        verified,
    )

    assert evidence != -1
    assert evidence < verified


def test_verified_success_hook_is_after_step_completion():
    text = agent_source()

    verified = text.index(
        "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
    )

    complete = text.rfind(
        "self.task_state.complete_step(",
        0,
        verified,
    )

    assert complete != -1
    assert complete < verified


def test_verified_success_hook_is_before_location_completion():
    text = agent_source()

    hook = text.index(
        "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
    )

    location = text.index(
        "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        hook,
    )

    assert hook < location


def test_verified_success_hook_is_before_goal_decision():
    text = agent_source()

    hook = text.index(
        "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
    )

    goal = text.index(
        "# GOAL DECISION",
        hook,
    )

    assert hook < goal


def test_failure_hook_reassigns_shadow_result():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
        'if (\n                    tool_name == "get_current_location"',
    )

    normalized = " ".join(
        block.split()
    )

    assert (
        "shadow_result = ( execution_feedback_projection.shadow_result )"
        in normalized
    )

def test_verification_failure_hook_reassigns_shadow_result():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
        "final_response = (",
    )

    normalized = " ".join(
        block.split()
    )

    assert (
        "shadow_result = ( execution_feedback_projection.shadow_result )"
        in normalized
    )

def test_verified_success_hook_reassigns_shadow_result():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK",
        "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
    )

    normalized = " ".join(
        block.split()
    )

    assert (
        "shadow_result = ( execution_feedback_projection.shadow_result )"
        in normalized
    )

def test_all_1d_hooks_use_existing_task_state():
    text = agent_source()

    assert (
        text.count(
            "task_state=self.task_state"
        )
        >= 3
    )


def test_all_1d_hooks_use_registered_tool_names():
    text = agent_source()

    one_d_start = text.index(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK"
    )

    one_d_end = text.index(
        "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        text.index(
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
        ),
    )

    block = text[
        one_d_start:one_d_end
    ]

    assert (
        block.count(
            "self.tool_registry.keys()"
        )
        == 3
    )


def test_all_1d_hooks_reuse_resolver_gated_memory_context():
    text = agent_source()

    one_d_start = text.index(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK"
    )

    one_d_end = text.index(
        "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        text.index(
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
        ),
    )

    block = text[
        one_d_start:one_d_end
    ]

    assert (
        block.count(
            "memory_context=memory_context"
        )
        == 3
    )


def test_1d_hooks_use_action_result_effect_started():
    text = agent_source()

    assert (
        text.count(
            "effect_started=getattr("
        )
        == 3
    )

    assert (
        text.count(
            '"effect_started",'
        )
        >= 3
    )

def test_execution_failure_hook_declares_false_false():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
        'if (\n                    tool_name == "get_current_location"',
    )

    assert (
        "execution_success=False"
        in block
    )
    assert "verified=False" in block


def test_verification_failure_hook_uses_real_execution_success():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
        "final_response = (",
    )

    assert (
        "execution_success=action_result.success"
        in block
    )
    assert "verified=verified" in block


def test_verified_success_hook_uses_real_execution_and_verification_flags():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK",
        "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
    )

    assert (
        "execution_success=action_result.success"
        in block
    )
    assert "verified=verified" in block


def test_execution_failure_hook_does_not_change_control_flow():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
        'if (\n                    tool_name == "get_current_location"',
    )

    code_lines = tuple(
        line.lstrip()
        for line in block.splitlines()
        if not line.lstrip().startswith("#")
    )

    assert not any(
        line.startswith("return ")
        for line in code_lines
    )

    assert not any(
        line == "continue"
        or line.startswith("continue ")
        for line in code_lines
    )

def test_verification_failure_hook_does_not_change_control_flow():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
        "final_response = (",
    )

    assert "return " not in block
    assert "continue" not in block


def test_verified_success_hook_does_not_change_control_flow():
    block = hook_block(
        "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK",
        "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
    )

    assert "return " not in block
    assert "continue" not in block


def test_1d_hooks_do_not_call_executor():
    text = agent_source()

    for marker, end in (
        (
            "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
            'if (\n                    tool_name == "get_current_location"',
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
            "final_response = (",
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK",
            "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        ),
    ):
        block = hook_block(
            marker,
            end,
        )

        assert "self.executor" not in block


def test_1d_hooks_do_not_request_confirmation():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK"
    )

    end = text.index(
        "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        text.index(
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
        ),
    )

    block = text[
        start:end
    ]

    assert (
        "request_confirmation("
        not in block
    )


def test_1d_hooks_do_not_mutate_task_state():
    text = agent_source()

    markers = (
        (
            "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
            'if (\n                    tool_name == "get_current_location"',
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
            "final_response = (",
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK",
            "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        ),
    )

    forbidden = (
        "record_action(",
        "record_failure(",
        "set_evidence(",
        "add_observation(",
        "complete_step(",
        "mark_finished(",
        "begin_step(",
    )

    for marker, end in markers:
        block = hook_block(
            marker,
            end,
        )

        for item in forbidden:
            assert item not in block


def test_1d_hooks_do_not_mutate_messages():
    for marker, end in (
        (
            "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
            'if (\n                    tool_name == "get_current_location"',
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
            "final_response = (",
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK",
            "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        ),
    ):
        block = hook_block(
            marker,
            end,
        )

        assert "messages.append" not in block
        assert "messages.insert" not in block

def test_1d_hooks_do_not_emit_user_status():
    for marker, end in (
        (
            "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
            'if (\n                    tool_name == "get_current_location"',
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
            "final_response = (",
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK",
            "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        ),
    ):
        block = hook_block(
            marker,
            end,
        )

        assert "emit_status(" not in block

def test_1d_hooks_are_exception_isolated():
    text = agent_source()

    for marker, end in (
        (
            "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK",
            'if (\n                    tool_name == "get_current_location"',
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFICATION FAILURE FEEDBACK",
            "final_response = (",
        ),
        (
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK",
            "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        ),
    ):
        block = hook_block(
            marker,
            end,
        )

        assert "try:" in block
        assert (
            "except Exception as error:"
            in block
        )


def test_1d_hooks_do_not_use_tactical_loop():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1D — EXECUTION FAILURE FEEDBACK"
    )

    end = text.index(
        "# KUMA LOCATION-1 VERIFIED SENSOR COMPLETION",
        text.index(
            "# KUMA-INTEGRATION-1D — VERIFIED SUCCESS FEEDBACK"
        ),
    )

    block = text[
        start:end
    ]

    assert "ContinuousTacticalLoop" not in block
    assert "TacticalLoopFrame" not in block
    assert "evaluate_iteration(" not in block


def test_1d_hooks_explicitly_declare_feedback_boundaries():
    text = agent_source()

    assert (
        "FAILURE EVIDENCE != PERMISSION TO RETRY"
        in text
    )
    assert (
        "SUCCESS EVIDENCE != PERMISSION FOR NEXT ACTION"
        in text
    )
    assert (
        "FEEDBACK != MEMORY WRITE"
        in text
    )
    assert (
        "AUTHORITY:NONE"
        in text
    )


def test_existing_executor_call_count_remains_two():
    assert (
        agent_source().count(
            "self.executor.execute("
        )
        == 2
    )


def test_existing_verifier_call_count_remains_two():
    assert (
        agent_source().count(
            "verified = verify_result("
        )
        == 2
    )


def test_existing_verification_report_call_count_remains_two():
    assert (
        agent_source().count(
            "verification_report("
        )
        >= 2
    )
