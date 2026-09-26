
from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.agent.attention_surfacing as attention_module

from app.agent.attention_surfacing import (
    AttentionSurfacingObservation,
    evaluate_attention_surfacing,
    remember_seen_event,
)


ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "app/agent/kuma_agent.py"
MODULE = ROOT / "app/agent/attention_surfacing.py"

NOW = datetime(
    2026,
    9,
    13,
    12,
    0,
    tzinfo=timezone.utc,
)

EVENT_A = "a" * 64
EVENT_B = "b" * 64


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
                for alias
                in node.names
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


def hook_block():
    text = agent_source()

    start = text.index(
        "# KUMA-INTEGRATION-1E — PROACTIVE ATTENTION SURFACING"
    )

    end = text.index(
        "# ASK MODEL",
        start,
    )

    return text[
        start:end
    ]


def fake_engine(
    monkeypatch,
    *,
    selected=False,
    authority="NONE",
    event_authority="NONE",
    disposition="surface",
    reason="Relevant realtime change.",
    kind="location_change",
    event_id=EVENT_A,
    event_reason="A meaningful location change was detected.",
):
    class FakeDisposition:
        value = disposition

    selected_event = None

    if selected:
        selected_event = SimpleNamespace(
            authority=event_authority,
            event_id=event_id,
            kind=kind,
            reason=event_reason,
        )

    decision = SimpleNamespace(
        authority=authority,
        disposition=FakeDisposition(),
        reason=reason,
        selected_event=selected_event,
    )

    class FakeEngine:
        def decide(
            self,
            signals,
            context,
        ):
            return decision

    monkeypatch.setattr(
        attention_module,
        "ProactiveAttentionEngine",
        FakeEngine,
    )


def test_observation_is_frozen():
    value = AttentionSurfacingObservation(
        disposition="ignore",
        reason="No surfacing.",
        should_surface=False,
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        value.reason = "changed"


def test_observation_authority_is_none():
    value = AttentionSurfacingObservation(
        disposition="ignore",
        reason="No surfacing.",
        should_surface=False,
    )

    assert value.authority == "NONE"


def test_non_surface_observation_has_no_selected_event_data():
    value = AttentionSurfacingObservation(
        disposition="ignore",
        reason="No surfacing.",
        should_surface=False,
    )

    assert value.selected_event_id == ""
    assert value.selected_event_kind == ""
    assert value.status_text == ""


def test_surface_observation_requires_event_id():
    with pytest.raises(
        ValueError,
        match="event ID",
    ):
        AttentionSurfacingObservation(
            disposition="surface",
            reason="Surface.",
            should_surface=True,
            selected_event_kind="change",
            status_text="Attention",
        )


def test_surface_observation_requires_event_kind():
    with pytest.raises(
        ValueError,
        match="event kind",
    ):
        AttentionSurfacingObservation(
            disposition="surface",
            reason="Surface.",
            should_surface=True,
            selected_event_id=EVENT_A,
            status_text="Attention",
        )


def test_surface_observation_requires_status_text():
    with pytest.raises(
        ValueError,
        match="status text",
    ):
        AttentionSurfacingObservation(
            disposition="surface",
            reason="Surface.",
            should_surface=True,
            selected_event_id=EVENT_A,
            selected_event_kind="change",
        )


def test_non_surface_observation_rejects_event_data():
    with pytest.raises(
        ValueError,
        match="cannot carry",
    ):
        AttentionSurfacingObservation(
            disposition="ignore",
            reason="Ignore.",
            should_surface=False,
            selected_event_id=EVENT_A,
        )


def test_selected_event_id_must_be_sha256():
    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        AttentionSurfacingObservation(
            disposition="surface",
            reason="Surface.",
            should_surface=True,
            selected_event_id="bad",
            selected_event_kind="change",
            status_text="Attention",
        )


def test_should_surface_must_be_bool():
    with pytest.raises(
        TypeError,
        match="bool",
    ):
        AttentionSurfacingObservation(
            disposition="surface",
            reason="Surface.",
            should_surface=1,
            selected_event_id=EVENT_A,
            selected_event_kind="change",
            status_text="Attention",
        )


def test_empty_real_signal_batch_does_not_surface():
    result = evaluate_attention_surfacing(
        signals=(),
        current_time=NOW,
    )

    assert result.should_surface is False
    assert result.authority == "NONE"
    assert result.selected_event_id == ""
    assert result.status_text == ""


def test_empty_real_signal_batch_returns_nonblank_disposition():
    result = evaluate_attention_surfacing(
        signals=(),
        current_time=NOW,
    )

    assert result.disposition
    assert result.reason


def test_fake_selected_event_surfaces(monkeypatch):
    fake_engine(
        monkeypatch,
        selected=True,
    )

    result = evaluate_attention_surfacing(
        signals=(),
        current_time=NOW,
    )

    assert result.should_surface is True
    assert result.selected_event_id == EVENT_A
    assert result.selected_event_kind == "location_change"
    assert result.authority == "NONE"


def test_surface_status_uses_bounded_privacy_minimized_event_metadata(monkeypatch):
    fake_engine(
        monkeypatch,
        selected=True,
        kind="weather_change",
        event_reason="Weather changed meaningfully.",
    )

    result = evaluate_attention_surfacing(
        signals=(),
        current_time=NOW,
    )

    assert (
        result.status_text
        == "KUMA attention — weather_change: Weather changed meaningfully."
    )


def test_surface_status_is_bounded(monkeypatch):
    fake_engine(
        monkeypatch,
        selected=True,
        event_reason="x" * 2000,
    )

    result = evaluate_attention_surfacing(
        signals=(),
        current_time=NOW,
    )

    assert len(result.status_text) <= 280


def test_decision_authority_tamper_fails_closed(monkeypatch):
    fake_engine(
        monkeypatch,
        selected=False,
        authority="AUTHORIZED",
    )

    with pytest.raises(
        ValueError,
        match="Decision authority",
    ):
        evaluate_attention_surfacing(
            signals=(),
            current_time=NOW,
        )


def test_selected_event_authority_tamper_fails_closed(monkeypatch):
    fake_engine(
        monkeypatch,
        selected=True,
        event_authority="AUTHORIZED",
    )

    with pytest.raises(
        ValueError,
        match="selected ProactiveEvent",
    ):
        evaluate_attention_surfacing(
            signals=(),
            current_time=NOW,
        )


def test_naive_current_time_fails_closed():
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        evaluate_attention_surfacing(
            signals=(),
            current_time=datetime(
                2026,
                9,
                13,
                12,
                0,
            ),
        )


def test_wrong_current_time_type_fails_closed():
    with pytest.raises(
        TypeError,
        match="current_time",
    ):
        evaluate_attention_surfacing(
            signals=(),
            current_time="now",
        )


def test_signals_cannot_be_string():
    with pytest.raises(
        TypeError,
        match="signals",
    ):
        evaluate_attention_surfacing(
            signals="signal",
            current_time=NOW,
        )


def test_signals_reject_wrong_member_type():
    with pytest.raises(
        TypeError,
        match="RealtimeSignal",
    ):
        evaluate_attention_surfacing(
            signals=(
                object(),
            ),
            current_time=NOW,
        )


def test_signals_are_bounded_before_engine():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        evaluate_attention_surfacing(
            signals=tuple(
                object()
                for _ in range(33)
            ),
            current_time=NOW,
        )


def test_seen_ids_cannot_be_string():
    with pytest.raises(
        TypeError,
        match="seen_event_ids",
    ):
        evaluate_attention_surfacing(
            signals=(),
            seen_event_ids=EVENT_A,
            current_time=NOW,
        )


def test_seen_ids_must_be_sha256():
    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        evaluate_attention_surfacing(
            signals=(),
            seen_event_ids=(
                "bad",
            ),
            current_time=NOW,
        )


def test_acknowledged_ids_cannot_be_string():
    with pytest.raises(
        TypeError,
        match="acknowledged_event_ids",
    ):
        evaluate_attention_surfacing(
            signals=(),
            acknowledged_event_ids=EVENT_A,
            current_time=NOW,
        )


def test_acknowledged_ids_must_be_sha256():
    with pytest.raises(
        ValueError,
        match="SHA-256",
    ):
        evaluate_attention_surfacing(
            signals=(),
            acknowledged_event_ids=(
                "bad",
            ),
            current_time=NOW,
        )


def test_seen_ids_are_bounded():
    with pytest.raises(
        ValueError,
        match="bounded",
    ):
        evaluate_attention_surfacing(
            signals=(),
            seen_event_ids=tuple(
                f"{index:064x}"
                for index in range(33)
            ),
            current_time=NOW,
        )


def test_context_strings_are_bounded(monkeypatch):
    captured = {}

    class FakeDisposition:
        value = "ignore"

    class FakeEngine:
        def decide(
            self,
            signals,
            context,
        ):
            captured["context"] = context

            return SimpleNamespace(
                authority="NONE",
                disposition=FakeDisposition(),
                reason="Ignore.",
                selected_event=None,
            )

    monkeypatch.setattr(
        attention_module,
        "ProactiveAttentionEngine",
        FakeEngine,
    )

    evaluate_attention_surfacing(
        signals=(),
        active_goal="g" * 2000,
        remaining_objective="r" * 2000,
        mission_status="m" * 2000,
        current_time=NOW,
    )

    context = captured["context"]

    assert len(context.active_goal) <= 600
    assert len(context.remaining_objective) <= 600
    assert len(context.mission_status) <= 600


def test_seen_event_history_deduplicates():
    result = remember_seen_event(
        (
            EVENT_A,
            EVENT_B,
        ),
        EVENT_A,
    )

    assert result == (
        EVENT_B,
        EVENT_A,
    )


def test_seen_event_history_adds_new_event():
    result = remember_seen_event(
        (
            EVENT_A,
        ),
        EVENT_B,
    )

    assert result == (
        EVENT_A,
        EVENT_B,
    )


def test_seen_event_history_is_bounded():
    existing = tuple(
        f"{index:064x}"
        for index in range(32)
    )

    result = remember_seen_event(
        existing,
        "f" * 64,
    )

    assert len(result) == 32
    assert result[-1] == "f" * 64


def test_seen_does_not_mean_acknowledged(monkeypatch):
    captured = {}

    class FakeDisposition:
        value = "ignore"

    class FakeEngine:
        def decide(
            self,
            signals,
            context,
        ):
            captured["seen"] = (
                context.seen_event_ids
            )
            captured["acknowledged"] = (
                context.acknowledged_event_ids
            )

            return SimpleNamespace(
                authority="NONE",
                disposition=FakeDisposition(),
                reason="Ignore.",
                selected_event=None,
            )

    monkeypatch.setattr(
        attention_module,
        "ProactiveAttentionEngine",
        FakeEngine,
    )

    evaluate_attention_surfacing(
        signals=(),
        seen_event_ids=(
            EVENT_A,
        ),
        acknowledged_event_ids=(),
        current_time=NOW,
    )

    assert captured["seen"] == (
        EVENT_A,
    )
    assert captured["acknowledged"] == ()


def test_evaluate_signature_is_keyword_only():
    signature = inspect.signature(
        evaluate_attention_surfacing
    )

    for parameter in (
        signature.parameters.values()
    ):
        assert (
            parameter.kind
            == inspect.Parameter.KEYWORD_ONLY
        )


def test_evaluate_signature_has_exact_surface():
    signature = inspect.signature(
        evaluate_attention_surfacing
    )

    assert tuple(
        signature.parameters
    ) == (
        "signals",
        "active_goal",
        "remaining_objective",
        "mission_status",
        "seen_event_ids",
        "acknowledged_event_ids",
        "cues",
        "current_time",
    )


def test_module_imports_frozen_proactive_attention():
    assert (
        "app.agent.proactive_attention"
        in imports_for(
            MODULE
        )
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


def test_module_does_not_import_permissions():
    imports = imports_for(
        MODULE
    )

    assert all(
        "permission" not in name
        for name in imports
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


def test_module_does_not_import_model_client():
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


def test_module_never_calls_runtime_tick():
    assert (
        "tick"
        not in calls_for(
            MODULE
        )
    )


def test_module_never_calls_pending_signals():
    assert (
        "pending_signals"
        not in calls_for(
            MODULE
        )
    )


def test_module_never_drains_signals():
    assert (
        "drain_signals"
        not in calls_for(
            MODULE
        )
    )


def test_module_never_refreshes_provider():
    calls = calls_for(
        MODULE
    )

    assert "refresh_weather" not in calls
    assert "refresh_weather_daily" not in calls


def test_module_never_executes_tool():
    assert (
        "execute"
        not in calls_for(
            MODULE
        )
    )


def test_module_never_requests_confirmation():
    assert (
        "request_confirmation"
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


def test_module_never_notifies_user_directly():
    calls = calls_for(
        MODULE
    )

    assert "emit_status" not in calls
    assert "notify_user" not in calls
    assert "notify" not in calls


def test_agent_has_exactly_one_1e_marker():
    assert (
        agent_source().count(
            "# KUMA-INTEGRATION-1E — PROACTIVE ATTENTION SURFACING"
        )
        == 1
    )


def test_1e_hook_is_inside_agent_loop_before_model_call():
    text = agent_source()

    loop = text.index(
        "# AGENT LOOP"
    )

    hook = text.index(
        "# KUMA-INTEGRATION-1E — PROACTIVE ATTENTION SURFACING",
        loop,
    )

    ask = text.index(
        "# ASK MODEL",
        hook,
    )

    assert loop < hook < ask


def test_1e_hook_is_after_step_thinking_status():
    text = agent_source()

    hook = text.index(
        "# KUMA-INTEGRATION-1E — PROACTIVE ATTENTION SURFACING"
    )

    thinking = text.rfind(
        'self.emit_status(',
        0,
        hook,
    )

    assert thinking != -1
    assert thinking < hook


def test_1e_hook_runs_only_on_first_reasoning_step():
    block = hook_block()

    assert (
        "if step == 1:"
        in block
    )


def test_1e_hook_uses_non_destructive_pending_signals():
    block = hook_block()

    assert (
        block.count(
            "realtime_runtime.pending_signals()"
        )
        == 1
    )

    assert (
        "drain_signals("
        not in block
    )


def test_1e_hook_does_not_tick_runtime():
    block = hook_block()

    assert (
        "realtime_runtime.tick("
        not in block
    )


def test_1e_hook_does_not_refresh_weather():
    block = hook_block()

    assert (
        "refresh_weather("
        not in block
    )
    assert (
        "refresh_weather_daily("
        not in block
    )


def test_1e_hook_does_not_request_location():
    block = hook_block()

    assert (
        "get_current_location"
        not in block
    )


def test_1e_hook_passes_task_goal_as_audit_context():
    block = hook_block()

    assert (
        "active_goal=("
        in block
    )
    assert (
        "self.task_state.goal"
        in block
    )


def test_1e_hook_passes_remaining_objective_as_audit_context():
    block = hook_block()

    assert (
        "remaining_objective=("
        in block
    )
    assert (
        "self.task_state.remaining_objective"
        in block
    )


def test_1e_hook_supplies_no_invented_attention_cues():
    block = hook_block()

    assert "cues=()" in block


def test_1e_hook_does_not_fake_user_acknowledgement():
    block = hook_block()

    assert (
        "acknowledged_event_ids=()"
        in block
    )


def test_1e_hook_uses_bounded_seen_event_history():
    block = hook_block()

    assert (
        '_raphael_attention_seen_event_ids'
        in block
    )
    assert (
        "remember_seen_event("
        in block
    )


def test_1e_hook_updates_seen_only_after_surface():
    block = hook_block()

    surface = block.index(
        "if attention_observation.should_surface:"
    )

    status = block.index(
        "self.emit_status(",
        surface,
    )

    remember = block.index(
        "remember_seen_event(",
        status,
    )

    assign = block.index(
        "self._raphael_attention_seen_event_ids",
        remember,
    )

    assert surface < status < remember < assign


def test_1e_hook_uses_existing_status_surface():
    block = hook_block()

    assert (
        "self.emit_status("
        in block
    )

    assert (
        "attention_observation.status_text"
        in block
    )


def test_1e_hook_has_no_model_message_mutation():
    block = hook_block()

    assert "messages.append" not in block
    assert "messages.insert" not in block


def test_1e_hook_has_no_task_state_mutation():
    block = hook_block()

    for name in (
        "record_action(",
        "record_failure(",
        "set_evidence(",
        "complete_step(",
        "mark_finished(",
        "begin_step(",
    ):
        assert name not in block


def test_1e_hook_has_no_executor_surface():
    block = hook_block()

    assert "self.executor" not in block
    assert ".execute(" not in block


def test_1e_hook_has_no_confirmation_surface():
    block = hook_block()

    assert "request_confirmation(" not in block
    assert "approved =" not in block


def test_1e_hook_has_no_permission_surface():
    block = hook_block()

    assert "get_permission_level(" not in block
    assert "require_explicit_permission(" not in block


def test_1e_hook_has_no_return_or_continue_control_flow():
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


def test_1e_hook_is_exception_isolated():
    block = hook_block()

    assert "try:" in block
    assert (
        "except Exception as error:"
        in block
    )


def test_1e_hook_declares_attention_boundaries():
    block = hook_block()

    assert "REALTIME SIGNAL != COMMAND" in block
    assert "ATTENTION != AUTHORITY" in block
    assert "SURFACE != EXECUTE" in block
    assert "NOTIFICATION != TOOL CALL" in block
    assert "AUTHORITY:NONE" in block


def test_1e_hook_does_not_use_tactical_loop():
    block = hook_block()

    assert "ContinuousTacticalLoop" not in block
    assert "TacticalLoopFrame" not in block
    assert "evaluate_iteration(" not in block


def test_1e_hook_does_not_change_shadow_result():
    block = hook_block()

    assert "shadow_result =" not in block


def test_agent_has_only_one_new_pending_signal_read_surface():
    text = agent_source()

    assert (
        text.count(
            "realtime_runtime.pending_signals()"
        )
        == 1
    )


def test_existing_runtime_tick_remains_separate_from_1e():
    text = agent_source()

    tick = text.index(
        "realtime_runtime.tick()"
    )

    hook = text.index(
        "# KUMA-INTEGRATION-1E — PROACTIVE ATTENTION SURFACING"
    )

    assert tick < hook
    assert (
        "realtime_runtime.tick()"
        not in hook_block()
    )
