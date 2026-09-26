from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.agent.kuma_agent import KumaAgent


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "app/agent/kuma_agent.py"
MISSION_A = ROOT / "app/agent/mission_cognitive_observation.py"


def agent_source():
    return AGENT.read_text()


def mission_a_source():
    return MISSION_A.read_text()


def marker_block(start_marker, end_marker):
    text = agent_source()
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def run_function():
    source = agent_source()
    tree = ast.parse(source, filename=str(AGENT))

    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "KumaAgent"
    )

    return next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "run"
    )


def run_source():
    source = agent_source()
    return ast.get_source_segment(
        source,
        run_function(),
    )


def test_empty_advisory_returns_original_messages_identity():
    messages = [
        {
            "role": "user",
            "content": "hello",
        }
    ]

    result = KumaAgent._build_ephemeral_mission_reasoning_messages(
        messages,
        "",
    )

    assert result is messages


def test_nonblank_advisory_returns_copy_without_mutating_source():
    messages = [
        {
            "role": "system",
            "content": "base",
        },
        {
            "role": "user",
            "content": "do the task",
        },
    ]

    before = [
        dict(item)
        for item in messages
    ]

    result = KumaAgent._build_ephemeral_mission_reasoning_messages(
        messages,
        "AUTHORITY:NONE advisory",
    )

    assert result is not messages
    assert messages == before
    assert result[:-1] == messages

    assert result[-1] == {
        "role": "system",
        "content": "AUTHORITY:NONE advisory",
    }


def test_ephemeral_helper_bounds_advisory():
    result = KumaAgent._build_ephemeral_mission_reasoning_messages(
        [],
        "x" * 5000,
    )

    assert len(result[-1]["content"]) == 2200


def test_ephemeral_helper_preserves_current_user_request_exactly():
    messages = [
        {
            "role": "system",
            "content": "base",
        },
        {
            "role": "user",
            "content": "Open Notes.",
        },
    ]

    result = KumaAgent._build_ephemeral_mission_reasoning_messages(
        messages,
        "AUTHORITY:NONE advisory",
    )

    users = [
        item
        for item in result
        if isinstance(item, dict)
        and item.get("role") == "user"
    ]

    assert users == [
        {
            "role": "user",
            "content": "Open Notes.",
        }
    ]


def test_mission_b_has_exactly_one_marker_for_each_stage():
    text = agent_source()

    for marker in (
        "KUMA-MISSION-B — EPHEMERAL REASONING MESSAGE COPY",
        "KUMA-MISSION-B — ONE-SHOT ADVISORY HOLDER",
        "KUMA-MISSION-B — CONSUME ONE-SHOT ADVISORY",
        "KUMA-MISSION-B — CAPTURE NEXT-STEP ADVISORY",
    ):
        assert text.count(marker) == 1


def test_one_shot_holder_is_local_not_agent_state():
    text = agent_source()

    assert 'mission_cognitive_advisory = ""' in text
    assert "self.mission_cognitive_advisory" not in text
    assert "self._mission_cognitive" not in text


def test_holder_is_initialized_before_reasoning_loop():
    text = agent_source()

    holder = text.index(
        "# KUMA-MISSION-B — ONE-SHOT ADVISORY HOLDER"
    )

    loop = text.index(
        "for step in range(",
        holder,
    )

    assert holder < loop


def test_consumption_is_before_normal_ask_model_call():
    text = agent_source()

    consume = text.index(
        "# KUMA-MISSION-B — CONSUME ONE-SHOT ADVISORY"
    )

    ask = text.index(
        "response = self.ask_model(",
        consume,
    )

    assert consume < ask


def test_normal_ask_model_preserves_frozen_messages_call_shape():
    block = marker_block(
        "# KUMA-MISSION-B — CONSUME ONE-SHOT ADVISORY",
        "# STORE MODEL RESPONSE",
    )

    historical = """response = self.ask_model(
                    messages
                )"""

    assert historical in block

    assert (
        "canonical_messages = (\n"
        "                    messages\n"
        "                )"
        in block
    )

    ask_index = block.index(
        historical
    )

    success_restore = (
        "messages = (\n"
        "                    canonical_messages\n"
        "                )"
    )

    success_restore_index = block.index(
        success_restore,
        ask_index,
    )

    assert ask_index < success_restore_index

    assert (
        "except Exception as error:\n\n"
        "                messages = (\n"
        "                    canonical_messages\n"
        "                )"
        in block
    )

    source = agent_source()

    tree = ast.parse(
        source,
        filename=str(
            AGENT
        ),
    )

    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "KumaAgent"
    )

    run = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "run"
    )

    stale_names = [
        node
        for node in ast.walk(run)
        if isinstance(node, ast.Name)
        and node.id == "mission_reasoning_messages"
    ]

    assert stale_names == []


def test_advisory_is_consumed_before_model_call():
    block = marker_block(
        "# KUMA-MISSION-B — CONSUME ONE-SHOT ADVISORY",
        "# STORE MODEL RESPONSE",
    )

    assert block.index(
        'mission_cognitive_advisory = ""'
    ) < block.index(
        "response = self.ask_model("
    )


def test_helper_only_appends_to_ephemeral_copy():
    source = agent_source()
    tree = ast.parse(
        source,
        filename=str(
            AGENT
        ),
    )

    cls = next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.ClassDef,
            )
            and node.name == "KumaAgent"
        )
    )

    helper = next(
        node
        for node in cls.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == "_build_ephemeral_mission_reasoning_messages"
        )
    )

    append_receivers = []

    for node in ast.walk(
        helper
    ):
        if not (
            isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Attribute,
            )
            and node.func.attr
            == "append"
        ):
            continue

        receiver = ast.get_source_segment(
            source,
            node.func.value,
        )

        append_receivers.append(
            receiver
        )

    assert append_receivers == [
        "ephemeral_messages"
    ]

    assert "messages" not in append_receivers


def test_capture_is_after_integration_1f_and_before_build_action():
    text = agent_source()

    integrated = text.index(
        "# KUMA-INTEGRATION-1F — BOUNDED INTEGRATED COGNITIVE LOOP"
    )

    capture = text.index(
        "# KUMA-MISSION-B — CAPTURE NEXT-STEP ADVISORY"
    )

    build = text.index(
        "# BUILD ACTION",
        integrated,
    )

    assert integrated < capture < build


def test_capture_uses_exact_live_integrated_observation():
    block = marker_block(
        "# KUMA-MISSION-B — CAPTURE NEXT-STEP ADVISORY",
        "# BUILD ACTION",
    )

    assert "project_mission_cognitive_observation(" in block
    assert "integrated_loop_observation" in block
    assert ".to_reasoning_context()" in block


def test_capture_cannot_override_current_control_flow():
    block = marker_block(
        "# KUMA-MISSION-B — CAPTURE NEXT-STEP ADVISORY",
        "# BUILD ACTION",
    )

    assert "return " not in block
    assert "continue" not in block
    assert "break" not in block


def test_capture_is_exception_isolated_and_clears_on_failure():
    block = marker_block(
        "# KUMA-MISSION-B — CAPTURE NEXT-STEP ADVISORY",
        "# BUILD ACTION",
    )

    assert "except Exception as error:" in block
    assert 'mission_cognitive_advisory = ""' in block


@pytest.mark.parametrize(
    "forbidden",
    (
        "mission_service",
        "execute_mission(",
        "execute_mission_step(",
        "resume_mission(",
        "get_permission_level(",
        "confirmation_callback(",
        "executor.execute(",
        "task_state.",
        "save_memory",
        "save_message",
        "pending_signals(",
        ".tick(",
    ),
)
def test_capture_has_no_authority_or_side_effect_surface(forbidden):
    block = marker_block(
        "# KUMA-MISSION-B — CAPTURE NEXT-STEP ADVISORY",
        "# BUILD ACTION",
    )

    assert forbidden not in block


def test_consumption_has_no_authority_or_side_effect_surface():
    block = marker_block(
        "# KUMA-MISSION-B — CONSUME ONE-SHOT ADVISORY",
        "# STORE MODEL RESPONSE",
    )

    for forbidden in (
        "mission_service",
        "execute_mission(",
        "execute_mission_step(",
        "resume_mission(",
        "get_permission_level(",
        "confirmation_callback(",
        "executor.execute(",
        "task_state.",
        "save_memory",
        "save_message",
        "pending_signals(",
        ".tick(",
    ):
        assert forbidden not in block


def test_mission_b_retains_exactly_one_normal_ask_model_call_site():
    run = run_function()

    calls = [
        node
        for node in ast.walk(run)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "ask_model"
    ]

    assert len(calls) == 1


def test_mission_b_retains_one_realtime_pending_signal_read():
    assert run_source().count(
        "realtime_runtime.pending_signals()"
    ) == 1


def test_capture_does_not_store_projection_on_agent():
    block = marker_block(
        "# KUMA-MISSION-B — CAPTURE NEXT-STEP ADVISORY",
        "# BUILD ACTION",
    )

    assert "self." not in block


def test_capture_does_not_mutate_canonical_messages():
    block = marker_block(
        "# KUMA-MISSION-B — CAPTURE NEXT-STEP ADVISORY",
        "# BUILD ACTION",
    )

    assert "messages." not in block


def test_consumption_does_not_mutate_canonical_messages():
    block = marker_block(
        "# KUMA-MISSION-B — CONSUME ONE-SHOT ADVISORY",
        "# STORE MODEL RESPONSE",
    )

    for marker in (
        "messages.append(",
        "messages.extend(",
        "messages.insert(",
    ):
        assert marker not in block


def test_mission_a_remains_zero_authority_projection_contract():
    text = mission_a_source()

    for marker in (
        "COGNITION != COMMAND",
        "MISSION COGNITION != MISSION EXECUTION",
        "PROJECTION != PERMISSION",
        "PROJECTION != CONFIRMATION",
        "PROJECTION != COMPLETION",
        "PROJECTION != RETRY",
        "PROJECTION != PERSISTENCE",
        "AUTHORITY: NONE",
    ):
        assert marker in text


def test_mission_b_declares_required_boundaries():
    text = agent_source()

    for marker in (
        "ADVISORY != COMMAND",
        "SYSTEM ROLE != RUNTIME AUTHORITY",
        "COPY != CONVERSATION PERSISTENCE",
        "INJECTION != TOOL AUTHORIZATION",
        "ONE-SHOT != BACKGROUND STATE",
        "CURRENT-TURN COGNITION != CURRENT-STEP COMMAND",
        "NEXT-STEP ADVISORY != AUTHORIZATION",
        "LOCAL VALUE != CROSS-TURN MEMORY",
        "ADVISORY != USER REQUEST",
        "ADVISORY != TOOL ARGUMENTS",
        "ADVISORY != PERMISSION",
        "ADVISORY != CONFIRMATION",
        "ADVISORY != EXECUTION",
        "PROJECTION != CONTROL FLOW",
        "PROJECTION != CURRENT ACTION MUTATION",
        "CAPTURE != PERSISTENCE",
        "FAILURE != TURN CANCELLATION",
    ):
        assert marker in text
