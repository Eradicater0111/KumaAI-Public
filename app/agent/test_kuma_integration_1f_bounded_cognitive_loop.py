
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
    LoopDisposition,
    TacticalLoopState,
)


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "app/agent/kuma_agent.py"
MODULE = ROOT / "app/agent/integrated_cognitive_loop.py"

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


def live_pair(
    *,
    tool_name="inspect_system",
    arguments=None,
    tools=None,
):
    if arguments is None:
        arguments = {}

    if tools is None:
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
        tool_name=tool_name,
        arguments=arguments,
        available_tool_names=tools,
    )

    return shadow, action


def evaluate(
    *,
    state=None,
    tool_name="inspect_system",
    arguments=None,
    tools=None,
):
    if state is None:
        state = TacticalLoopState()

    shadow, action = live_pair(
        tool_name=tool_name,
        arguments=arguments,
        tools=tools,
    )

    return evaluate_integrated_loop_iteration(
        shadow_result=shadow,
        action_evaluation=action,
        loop_state=state,
        signals=(),
        active_goal="Inspect current state safely.",
        remaining_objective="",
        mission_status="",
        seen_event_ids=(),
        acknowledged_event_ids=(),
        cues=(),
        current_time=NOW,
    )


def hook_block():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1F — BOUNDED INTEGRATED COGNITIVE LOOP"
    )

    end = text.index(
        "# BUILD ACTION",
        start,
    )

    return text[
        start:end
    ]


def test_status_surface_is_exact():
    assert {
        item.name
        for item in IntegratedLoopStatus
    } == {
        "OBSERVED",
        "SKIPPED",
    }


def test_observation_is_frozen():
    result = evaluate()

    with pytest.raises(
        FrozenInstanceError
    ):
        result.reason = "changed"


def test_observation_authority_is_none():
    result = evaluate()

    assert result.authority == "NONE"


def test_observed_contains_attention_decision():
    result = evaluate()

    assert (
        result.status
        == IntegratedLoopStatus.OBSERVED
    )

    assert (
        result.attention_decision
        is not None
    )


def test_observed_contains_iteration():
    result = evaluate()

    assert result.iteration is not None


def test_attention_authority_is_none():
    result = evaluate()

    assert (
        result.attention_decision.authority
        == "NONE"
    )


def test_iteration_authority_is_none():
    result = evaluate()

    assert result.iteration.authority == "NONE"


def test_next_state_authority_is_none():
    result = evaluate()

    assert result.next_state.authority == "NONE"


def test_next_state_matches_iteration():
    result = evaluate()

    assert (
        result.next_state
        == result.iteration.next_state
    )


def test_world_state_is_exact_shadow_snapshot():
    shadow, action = live_pair()

    result = evaluate_integrated_loop_iteration(
        shadow_result=shadow,
        action_evaluation=action,
        loop_state=TacticalLoopState(),
        current_time=NOW,
    )

    assert (
        result.iteration.frame.world_state
        is shadow.snapshot
    )


def test_situation_is_exact_shadow_situation():
    shadow, action = live_pair()

    result = evaluate_integrated_loop_iteration(
        shadow_result=shadow,
        action_evaluation=action,
        loop_state=TacticalLoopState(),
        current_time=NOW,
    )

    assert (
        result.iteration.frame.situation
        is shadow.situation
    )


def test_candidate_is_exact_live_1b_tactical_option():
    shadow, action = live_pair()

    result = evaluate_integrated_loop_iteration(
        shadow_result=shadow,
        action_evaluation=action,
        loop_state=TacticalLoopState(),
        current_time=NOW,
    )

    assert (
        result.iteration.frame.candidate_options
        == (
            action.candidate.option,
        )
    )


def test_tactical_decision_is_exact_live_1b_decision():
    shadow, action = live_pair()

    result = evaluate_integrated_loop_iteration(
        shadow_result=shadow,
        action_evaluation=action,
        loop_state=TacticalLoopState(),
        current_time=NOW,
    )

    assert (
        result.iteration.frame.tactical_decision
        is action.decision
    )


def test_attention_decision_is_exact_frame_decision():
    result = evaluate()

    assert (
        result.iteration.frame.attention_decision
        is result.attention_decision
    )


def test_completion_is_never_manufactured():
    result = evaluate()

    completion = (
        result.iteration.frame.completion
    )

    assert completion.verified_complete is False
    assert completion.evidence_digest == ""
    assert completion.reason == ""


def test_live_verified_tool_success_is_not_overall_completion():
    result = evaluate()

    assert (
        result.iteration.disposition
        != LoopDisposition.COMPLETE
    )


def test_first_iteration_advances_caller_owned_state():
    result = evaluate()

    assert (
        result.next_state.iterations_seen
        == 1
    )


def test_second_iteration_accepts_previous_next_state():
    first = evaluate()

    second = evaluate(
        state=first.next_state
    )

    assert (
        second.next_state.iterations_seen
        == 2
    )


def test_adapter_does_not_mutate_input_state():
    state = TacticalLoopState()

    before = (
        state.iterations_seen,
        state.previous_cognitive_digest,
        state.repeated_state_count,
    )

    evaluate(
        state=state
    )

    after = (
        state.iterations_seen,
        state.previous_cognitive_digest,
        state.repeated_state_count,
    )

    assert before == after


def test_loop_state_must_be_exact_type():
    shadow, action = live_pair()

    with pytest.raises(
        TypeError,
        match="TacticalLoopState",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=action,
            loop_state=object(),
            current_time=NOW,
        )


def test_shadow_result_must_be_exact_type():
    _, action = live_pair()

    with pytest.raises(
        TypeError,
        match="ShadowCognitionResult",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=object(),
            action_evaluation=action,
            loop_state=TacticalLoopState(),
            current_time=NOW,
        )


def test_action_evaluation_must_be_exact_type():
    shadow, _ = live_pair()

    with pytest.raises(
        TypeError,
        match="ShadowActionEvaluation",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=object(),
            loop_state=TacticalLoopState(),
            current_time=NOW,
        )


def test_current_time_must_be_aware():
    shadow, action = live_pair()

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=action,
            loop_state=TacticalLoopState(),
            current_time=datetime(
                2026,
                9,
                13,
                12,
                0,
            ),
        )


def test_current_time_type_is_checked():
    shadow, action = live_pair()

    with pytest.raises(
        TypeError,
        match="current_time",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=action,
            loop_state=TacticalLoopState(),
            current_time="now",
        )


def test_empty_signals_are_valid():
    result = evaluate()

    assert result.attention_decision is not None


def test_signal_string_is_rejected():
    shadow, action = live_pair()

    with pytest.raises(
        TypeError,
        match="signals",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=action,
            loop_state=TacticalLoopState(),
            signals="signal",
            current_time=NOW,
        )


def test_wrong_signal_member_is_rejected():
    shadow, action = live_pair()

    with pytest.raises(
        TypeError,
        match="RealtimeSignal",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=action,
            loop_state=TacticalLoopState(),
            signals=(
                object(),
            ),
            current_time=NOW,
        )


def test_signal_batch_is_bounded():
    shadow, action = live_pair()

    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=action,
            loop_state=TacticalLoopState(),
            signals=tuple(
                object()
                for _ in range(33)
            ),
            current_time=NOW,
        )


def test_seen_event_ids_are_validated():
    shadow, action = live_pair()

    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=action,
            loop_state=TacticalLoopState(),
            seen_event_ids=(
                "bad",
            ),
            current_time=NOW,
        )


def test_acknowledged_event_ids_are_validated():
    shadow, action = live_pair()

    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        evaluate_integrated_loop_iteration(
            shadow_result=shadow,
            action_evaluation=action,
            loop_state=TacticalLoopState(),
            acknowledged_event_ids=(
                "bad",
            ),
            current_time=NOW,
        )


def test_context_strings_are_bounded():
    shadow, action = live_pair()

    result = evaluate_integrated_loop_iteration(
        shadow_result=shadow,
        action_evaluation=action,
        loop_state=TacticalLoopState(),
        active_goal="g" * 5000,
        remaining_objective="r" * 5000,
        mission_status="m" * 5000,
        current_time=NOW,
    )

    assert result.iteration is not None

def test_function_signature_is_keyword_only():
    signature = inspect.signature(
        evaluate_integrated_loop_iteration
    )

    for parameter in (
        signature.parameters.values()
    ):
        assert (
            parameter.kind
            == inspect.Parameter.KEYWORD_ONLY
        )


def test_function_signature_has_exact_surface():
    signature = inspect.signature(
        evaluate_integrated_loop_iteration
    )

    assert tuple(
        signature.parameters
    ) == (
        "shadow_result",
        "action_evaluation",
        "loop_state",
        "signals",
        "active_goal",
        "remaining_objective",
        "mission_status",
        "seen_event_ids",
        "acknowledged_event_ids",
        "cues",
        "current_time",
    )


def test_module_imports_frozen_1j():
    assert (
        "app.agent.proactive_attention"
        in imports_for(
            MODULE
        )
    )


def test_module_imports_frozen_1k():
    assert (
        "app.agent.tactical_loop"
        in imports_for(
            MODULE
        )
    )


def test_module_imports_live_1a_and_1b_contracts():
    imports = imports_for(
        MODULE
    )

    assert (
        "app.agent.shadow_cognition"
        in imports
    )
    assert (
        "app.agent.shadow_action_evaluation"
        in imports
    )


def test_module_imports_signal_contract_not_runtime():
    imports = imports_for(
        MODULE
    )

    assert (
        "app.realtime.change_detection"
        in imports
    )
    assert (
        "app.realtime.runtime"
        not in imports
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


def test_module_does_not_import_memory():
    assert all(
        not name.startswith(
            "app.memory"
        )
        for name in imports_for(
            MODULE
        )
    )


def test_module_does_not_import_model_clients():
    imports = imports_for(
        MODULE
    )

    assert "ollama" not in imports
    assert "google.genai" not in imports


def test_module_does_not_import_threading_asyncio_subprocess():
    imports = imports_for(
        MODULE
    )

    assert "threading" not in imports
    assert "asyncio" not in imports
    assert "subprocess" not in imports


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


def test_module_has_no_for_loop_that_drives_runtime():
    source = module_source()

    assert "while True" not in source
    assert "run_forever" not in source
    assert "background" not in calls_for(
        MODULE
    )


def test_module_never_calls_executor():
    assert (
        "execute"
        not in calls_for(
            MODULE
        )
    )


def test_module_never_requests_confirmation():
    calls = calls_for(
        MODULE
    )

    assert "request_confirmation" not in calls
    assert "confirmation_callback" not in calls


def test_module_never_reads_runtime_signals():
    calls = calls_for(
        MODULE
    )

    assert "pending_signals" not in calls
    assert "drain_signals" not in calls
    assert "tick" not in calls


def test_module_never_refreshes_provider():
    calls = calls_for(
        MODULE
    )

    assert "refresh_weather" not in calls
    assert "refresh_weather_daily" not in calls


def test_module_never_calls_model():
    calls = calls_for(
        MODULE
    )

    assert "ask_model" not in calls
    assert "generate_content" not in calls


def test_module_never_persists():
    calls = calls_for(
        MODULE
    )

    for name in (
        "save",
        "remember",
        "forget",
        "write_text",
        "write_bytes",
        "connect",
        "commit",
    ):
        assert name not in calls


def test_module_never_notifies_user():
    calls = calls_for(
        MODULE
    )

    assert "emit_status" not in calls
    assert "notify" not in calls
    assert "notify_user" not in calls


def test_module_calls_one_frozen_attention_decision():
    source = module_source()

    assert (
        source.count(
            "ProactiveAttentionEngine().decide("
        )
        == 1
    )


def test_module_calls_one_frozen_loop_iteration():
    source = module_source()

    assert (
        source.count(
            "ContinuousTacticalLoop().evaluate_iteration("
        )
        == 1
    )


def test_module_constructs_default_unverified_completion_only():
    source = module_source()

    assert (
        source.count(
            "VerifiedLoopCompletion()"
        )
        == 1
    )

    assert (
        "verified_complete=True"
        not in source
    )


def test_agent_has_exactly_one_1f_marker():
    assert (
        agent_source().count(
            "# KUMA-INTEGRATION-1F — BOUNDED INTEGRATED COGNITIVE LOOP"
        )
        == 1
    )


def test_1f_hook_is_after_1c_before_build_action():
    text = agent_source()

    one_c = text.index(
        "# KUMA-INTEGRATION-1C"
    )

    one_f = text.index(
        "# KUMA-INTEGRATION-1F — BOUNDED INTEGRATED COGNITIVE LOOP",
        one_c,
    )

    build = text.index(
        "# BUILD ACTION",
        one_f,
    )

    assert one_c < one_f < build


def test_agent_initializes_loop_state_once_before_for_loop():
    text = agent_source()

    init = text.index(
        "raphael_loop_state = None"
    )

    loop = text.index(
        "for step in range(",
        init,
    )

    assert init < loop

    assert (
        text.count(
            "raphael_loop_state = None"
        )
        == 1
    )


def test_agent_constructs_tactical_loop_state_once():
    text = agent_source()

    normalized = " ".join(
        text.split()
    )

    assert (
        normalized.count(
            "raphael_loop_state = ( TacticalLoopState() )"
        )
        == 1
    )

def test_loop_state_is_local_not_self_persistent():
    text = agent_source()

    assert (
        "self.raphael_loop_state"
        not in text
    )
    assert (
        "self._raphael_loop_state"
        not in text
    )


def test_agent_reuses_1e_pending_signal_snapshot():
    text = agent_source()

    normalized = " ".join(
        text.split()
    )

    assert (
        "raphael_loop_attention_signals = ( pending_attention_signals )"
        in normalized
    )

    assert (
        text.count(
            "realtime_runtime.pending_signals()"
        )
        == 1
    )

def test_agent_captures_seen_ids_before_1e_surfacing():
    text = agent_source()

    one_e = text.index(
        "# KUMA-INTEGRATION-1E — PROACTIVE ATTENTION SURFACING"
    )

    seen = text.rfind(
        "raphael_loop_seen_event_ids =",
        0,
        one_e,
    )

    assert seen != -1


def test_1f_hook_uses_exact_shadow_result():
    block = hook_block()

    assert (
        "shadow_result=shadow_result"
        in block
    )


def test_1f_hook_uses_exact_shadow_action_evaluation():
    block = hook_block()

    assert (
        "action_evaluation=shadow_action_evaluation"
        in block
    )


def test_1f_hook_uses_local_loop_state():
    block = hook_block()

    assert (
        "loop_state=raphael_loop_state"
        in block
    )


def test_1f_hook_reuses_attention_signal_snapshot():
    block = hook_block()

    assert (
        "signals=raphael_loop_attention_signals"
        in block
    )


def test_1f_hook_does_not_fake_cues_or_acknowledgement():
    block = hook_block()

    assert "cues=()" in block
    assert "acknowledged_event_ids=()" in block


def test_1f_hook_updates_only_local_loop_state():
    block = hook_block()

    normalized = " ".join(
        block.split()
    )

    assert (
        "raphael_loop_state = ( integrated_loop_observation.next_state )"
        in normalized
    )

    assert (
        "self.raphael_loop_state"
        not in block
    )

def test_1f_hook_does_not_change_kuma_control_flow():
    block = hook_block()

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


def test_1f_hook_does_not_call_executor():
    block = hook_block()

    assert "self.executor" not in block
    assert ".execute(" not in block


def test_1f_hook_does_not_request_confirmation():
    block = hook_block()

    assert "request_confirmation(" not in block
    assert "approved =" not in block


def test_1f_hook_does_not_read_permission():
    block = hook_block()

    assert "get_permission_level(" not in block
    assert "require_explicit_permission(" not in block


def test_1f_hook_does_not_mutate_messages():
    block = hook_block()

    assert "messages.append" not in block
    assert "messages.insert" not in block


def test_1f_hook_does_not_mutate_task_state():
    block = hook_block()

    for name in (
        "record_action(",
        "record_failure(",
        "set_evidence(",
        "complete_step(",
        "mark_finished(",
        "begin_step(",
        "set_remaining_objective(",
    ):
        assert name not in block


def test_1f_hook_does_not_surface_status():
    block = hook_block()

    assert "emit_status(" not in block


def test_1f_hook_does_not_read_runtime_again():
    block = hook_block()

    assert "pending_signals(" not in block
    assert "drain_signals(" not in block
    assert "realtime_runtime.tick(" not in block


def test_1f_hook_is_exception_isolated():
    block = hook_block()

    assert "try:" in block
    assert (
        "except Exception as error:"
        in block
    )


def test_1f_hook_declares_zero_authority_boundaries():
    block = hook_block()

    assert "LOOP ITERATION != EXECUTION" in block
    assert "ACTION_CANDIDATE != AUTHORIZATION" in block
    assert "WAIT_FOR_EVIDENCE != POLL" in block
    assert "BLOCKED != KUMA CONTROL-FLOW OVERRIDE" in block
    assert "AUTHORITY:NONE" in block


def test_1f_hook_does_not_create_verified_completion():
    block = hook_block()

    assert "VerifiedLoopCompletion" not in block
    assert "verified_complete=True" not in block


def test_existing_executor_call_count_remains_two():
    assert (
        agent_source().count(
            "self.executor.execute("
        )
        == 2
    )


def test_existing_confirmation_call_count_is_unchanged_surface():
    assert (
        agent_source().count(
            "self.request_confirmation("
        )
        >= 1
    )


def test_existing_pending_signals_call_count_remains_one():
    assert (
        agent_source().count(
            "realtime_runtime.pending_signals()"
        )
        == 1
    )


def test_1f_is_one_iteration_per_live_action_proposal():
    block = hook_block()

    assert (
        block.count(
            "evaluate_integrated_loop_iteration("
        )
        == 1
    )

    assert "while " not in block


def test_1f_observation_does_not_override_shadow_result():
    block = hook_block()

    assert "shadow_result =" not in block


def test_1f_observation_does_not_override_action_evaluation():
    block = hook_block()

    assert "shadow_action_evaluation =" not in block
