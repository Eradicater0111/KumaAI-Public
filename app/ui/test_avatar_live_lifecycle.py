from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.ui.avatar_runtime import (
    AvatarExpression,
    AvatarGaze,
    AvatarMode,
)


WINDOW = Path(__file__).with_name("window.py")


def source() -> str:
    return WINDOW.read_text()


def tree() -> ast.Module:
    return ast.parse(
        source(),
        filename=str(WINDOW),
    )


def kuma_window() -> ast.ClassDef:
    return next(
        node
        for node in tree().body
        if (
            isinstance(node, ast.ClassDef)
            and node.name == "KumaWindow"
        )
    )


def method_node(name: str) -> ast.FunctionDef:
    return next(
        node
        for node in kuma_window().body
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == name
        )
    )


def method_source(name: str) -> str:
    text = source()

    return (
        ast.get_source_segment(
            text,
            method_node(name),
        )
        or ""
    )


def test_window_imports_avatar_runtime_contract():
    text = source()

    assert "from app.ui.avatar_runtime import (" in text

    for required in (
        "AvatarExpression",
        "AvatarGaze",
        "AvatarMode",
        "AvatarSnapshot",
    ):
        assert required in text


def test_live_window_has_no_direct_floating_body_state_writes():
    assert "self.floating_body.set_state(" not in source()


def test_live_window_has_exact_semantic_snapshot_sink_count():
    assert (
        source().count(
            "self.body_controller.present_avatar_snapshot("
        )
        == 8
    )


def test_live_window_has_exact_avatar_snapshot_construction_count():
    assert source().count("AvatarSnapshot(") == 8


@pytest.mark.parametrize(
    ("name", "mode"),
    (
        ("_on_kuma_speech_started", "AvatarMode.SPEAKING"),
        ("_on_kuma_speech_finished", "AvatarMode.SUCCESS"),
        ("_on_kuma_speech_error", "AvatarMode.ERROR"),
        ("submit_user_turn_text", "AvatarMode.THINKING"),
        ("_restore_body_idle_if_current", "AvatarMode.IDLE"),
        ("on_error", "AvatarMode.ERROR"),
    ),
)
def test_single_mode_live_boundaries_use_semantic_snapshot(
    name,
    mode,
):
    text = method_source(name)

    assert "present_avatar_snapshot(" in text
    assert "AvatarSnapshot(" in text
    assert mode in text
    assert "self.floating_body.set_state(" not in text


def test_speech_started_binds_semantic_speaking_to_active_audio():
    text = method_source("_on_kuma_speech_started")

    assert "mode=AvatarMode.SPEAKING" in text
    assert "speech_active=True" in text
    assert 'reason="speech playback started"' in text


def test_speech_started_uses_user_gaze():
    assert (
        "gaze=AvatarGaze.USER"
        in method_source("_on_kuma_speech_started")
    )


def test_speech_started_uses_gentle_expression():
    assert (
        "expression=AvatarExpression.GENTLE"
        in method_source("_on_kuma_speech_started")
    )


def test_speech_started_cancels_old_idle_reset_first():
    text = method_source("_on_kuma_speech_started")

    assert (
        text.index("self._cancel_body_idle_reset()")
        < text.index("present_avatar_snapshot(")
    )


def test_speech_finished_preserves_pending_emotion_priority():
    text = method_source("_on_kuma_speech_finished")

    pending = text.index(
        "self._present_pending_emotion()"
    )

    semantic = text.index(
        "present_avatar_snapshot("
    )

    assert pending < semantic


def test_speech_finished_returns_when_pending_emotion_was_presented():
    text = method_source("_on_kuma_speech_finished")

    assert "if self._present_pending_emotion():" in text
    assert "return" in text


def test_speech_finished_is_success_presentation_not_speech_active():
    text = method_source("_on_kuma_speech_finished")

    assert "mode=AvatarMode.SUCCESS" in text
    assert "speech_active=True" not in text
    assert 'reason="speech playback completed"' in text


def test_speech_finished_schedules_terminal_reset():
    text = method_source("_on_kuma_speech_finished")

    assert "self._schedule_body_idle_reset(" in text
    assert "1400" in text


def test_speech_error_is_presentation_error_only():
    text = method_source("_on_kuma_speech_error")

    assert "mode=AvatarMode.ERROR" in text
    assert 'reason="speech playback failed"' in text

    for forbidden in (
        "self.runtime",
        "self.worker",
        "confirmation_requested",
        "request_confirmation(",
        "execute(",
        "mission",
        "TaskState",
    ):
        assert forbidden not in text


def test_speech_error_retains_existing_no_task_effect_docstring():
    assert (
        "Speech failure must never affect the underlying KUMA task."
        in method_source("_on_kuma_speech_error")
    )


def test_speech_error_still_schedules_visual_reset():
    text = method_source("_on_kuma_speech_error")

    assert "self._schedule_body_idle_reset(" in text


def test_send_message_uses_semantic_thinking_before_worker_start():
    text = (
        method_source("send_message")
        + method_source("submit_user_turn_text")
    )

    semantic = text.rindex(
        "present_avatar_snapshot("
    )

    worker_start = text.rindex(
        "worker.start()"
    )

    assert semantic < worker_start
    assert "mode=AvatarMode.THINKING" in text


def test_send_message_thinking_is_focused_presentation():
    text = (
        method_source("send_message")
        + method_source("submit_user_turn_text")
    )

    assert (
        "expression=AvatarExpression.FOCUSED"
        in text
    )
    assert "gaze=AvatarGaze.USER" in text
    assert 'reason="request started"' in text


def test_send_message_still_stops_previous_speech():
    text = (
        method_source("send_message")
        + method_source("submit_user_turn_text")
    )

    assert "self.speech.stop()" in text


def test_send_message_still_wires_legacy_runtime_status_bridge():
    text = (
        method_source("send_message")
        + method_source("submit_user_turn_text")
    )

    assert "worker.status_changed.connect(" in text
    assert (
        "self.body_controller.handle_runtime_status"
        in text
    )


def test_idle_restore_keeps_generation_guard():
    text = method_source(
        "_restore_body_idle_if_current"
    )

    assert "generation" in text
    assert "self._body_idle_generation" in text
    assert "return" in text
    assert "mode=AvatarMode.IDLE" in text


def test_idle_restore_is_neutral_and_zero_energy():
    text = method_source(
        "_restore_body_idle_if_current"
    )

    assert (
        "expression=AvatarExpression.NEUTRAL"
        in text
    )
    assert "motion_energy=0.0" in text
    assert (
        'reason="terminal presentation expired"'
        in text
    )


def test_on_response_has_both_failure_and_success_semantic_modes():
    text = method_source("on_response")

    assert "mode=AvatarMode.ERROR" in text
    assert "mode=AvatarMode.SUCCESS" in text


def test_on_response_failure_branch_keeps_existing_classifier():
    text = method_source("on_response")

    assert (
        "self._response_indicates_failure("
        in text
    )
    assert (
        'reason="response classified as failure"'
        in text
    )


def test_on_response_success_is_only_used_without_active_speech():
    text = method_source("on_response")

    assert "elif not speech_active:" in text
    assert (
        'reason="response completed without speech"'
        in text
    )


def test_on_response_still_requests_speech_before_terminal_presentation():
    text = method_source("on_response")

    speak = text.index(
        "self.speech.speak("
    )

    terminal = text.index(
        "self._response_indicates_failure("
    )

    assert speak < terminal


def test_on_response_does_not_claim_verified_goal_completion():
    text = method_source("on_response").lower()

    for forbidden in (
        "verified goal completion",
        "goal verified complete",
        "verified_complete=true",
        "mark_finished(",
        "task_state.mark_finished",
    ):
        assert forbidden not in text


def test_on_error_uses_semantic_error_presentation():
    text = method_source("on_error")

    assert "mode=AvatarMode.ERROR" in text
    assert (
        "expression=AvatarExpression.ALERT"
        in text
    )
    assert (
        'reason="worker or runtime error"'
        in text
    )


def test_on_error_still_restores_user_input_controls():
    text = method_source("on_error")

    assert "self.input.setEnabled(" in text
    assert "self.send_button.setEnabled(" in text
    assert "self.input.setFocus()" in text


def test_pending_emotion_remains_existing_expression_channel():
    text = method_source(
        "_present_pending_emotion"
    )

    assert (
        "self.body_controller.present_expression("
        in text
    )

    assert "present_avatar_snapshot(" not in text


def test_pending_emotion_still_schedules_its_directive_hold():
    text = method_source(
        "_present_pending_emotion"
    )

    assert "directive.hold_ms" in text


def test_window_still_uses_character_legacy_surface_separately():
    text = source()

    assert (
        text.count(
            "self.character.set_state("
        )
        == 5
    )


@pytest.mark.parametrize(
    "mode",
    tuple(AvatarMode),
)
def test_all_avatar_modes_remain_contract_members(
    mode,
):
    assert isinstance(mode.value, str)


@pytest.mark.parametrize(
    "expression",
    tuple(AvatarExpression),
)
def test_all_avatar_expressions_remain_contract_members(
    expression,
):
    assert isinstance(expression.value, str)


@pytest.mark.parametrize(
    "gaze",
    tuple(AvatarGaze),
)
def test_all_avatar_gaze_values_remain_contract_members(
    gaze,
):
    assert isinstance(gaze.value, str)


def test_window_does_not_import_renderer_adapter_directly():
    assert (
        "app.ui.avatar_renderer_adapter"
        not in source()
    )


def test_window_uses_controller_as_only_semantic_renderer_sink():
    text = source()

    assert "project_avatar_snapshot(" not in text


def test_live_wiring_does_not_touch_qml_or_3d_properties():
    text = source()

    for forbidden in (
        "rootObject(",
        "setProperty(",
        "bodyState",
        "eulerRotation",
        "inspectionYaw",
        "inspectionPitch",
        "hoverOffset",
    ):
        assert forbidden not in text


def test_live_wiring_does_not_add_permission_or_execution_calls():
    migrated = "\n".join(
        method_source(name)
        for name in (
            "_on_kuma_speech_started",
            "_on_kuma_speech_finished",
            "_on_kuma_speech_error",
            "send_message",
            "_restore_body_idle_if_current",
            "on_response",
            "on_error",
        )
    )

    for forbidden in (
        "get_permission_level(",
        "require_explicit_permission(",
        "register_tool(",
        ".executor.",
        ".execute(",
        "pending_signals(",
        "drain_signals(",
    ):
        assert forbidden not in migrated


def test_live_wiring_has_no_new_background_loop():
    for name in (
        "_on_kuma_speech_started",
        "_on_kuma_speech_finished",
        "_on_kuma_speech_error",
        "send_message",
        "_restore_body_idle_if_current",
        "on_response",
        "on_error",
    ):
        method = method_node(name)

        assert not any(
            isinstance(
                node,
                (
                    ast.While,
                    ast.AsyncFunctionDef,
                ),
            )
            for node in ast.walk(method)
        )


def test_live_wiring_documents_avatar_1c_boundaries():
    text = source()

    for required in (
        "UI EVENT != COGNITION",
        "VOICE EVENT != AUTHORITY",
        "SUCCESS PRESENTATION != VERIFIED GOAL COMPLETION",
        "ERROR PRESENTATION != TASK FAILURE AUTHORITY",
        "AVATAR TRANSITION != CONTROL FLOW",
        "RENDERER STATE != MODEL CONTEXT",
    ):
        assert required in text
