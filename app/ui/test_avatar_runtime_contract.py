from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
import inspect
from pathlib import Path

import pytest

from app.ui.avatar_runtime import (
    AVATAR_AUTHORITY_NONE,
    AvatarExpression,
    AvatarGaze,
    AvatarMode,
    AvatarSnapshot,
    default_avatar_snapshot,
)


MODULE = Path(__file__).with_name("avatar_runtime.py")


def source():
    return MODULE.read_text()


def imports():
    tree = ast.parse(source(), filename=str(MODULE))
    result = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            result.add(node.module)

    return result


def calls():
    tree = ast.parse(source(), filename=str(MODULE))
    result = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            result.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            result.append(node.func.attr)

    return result


def test_authority_constant_is_none():
    assert AVATAR_AUTHORITY_NONE == "NONE"


def test_mode_surface_is_exact():
    assert tuple(item.value for item in AvatarMode) == (
        "idle",
        "listening",
        "thinking",
        "speaking",
        "attention",
        "success",
        "error",
        "sleep",
    )


def test_expression_surface_is_exact():
    assert tuple(item.value for item in AvatarExpression) == (
        "neutral",
        "happy",
        "focused",
        "alert",
        "gentle",
    )


def test_gaze_surface_is_exact():
    assert tuple(item.value for item in AvatarGaze) == (
        "forward",
        "user",
        "target",
        "away",
    )


def test_snapshot_fields_are_exact():
    assert tuple(item.name for item in fields(AvatarSnapshot)) == (
        "mode",
        "expression",
        "expression_intensity",
        "gaze",
        "motion_energy",
        "speech_active",
        "reason",
        "authority",
    )


def test_authority_is_not_constructor_input():
    assert "authority" not in inspect.signature(AvatarSnapshot).parameters


def test_default_snapshot_values():
    snapshot = AvatarSnapshot()

    assert snapshot.mode == AvatarMode.IDLE
    assert snapshot.expression == AvatarExpression.NEUTRAL
    assert snapshot.expression_intensity == 0.0
    assert snapshot.gaze == AvatarGaze.FORWARD
    assert snapshot.motion_energy == 0.0
    assert snapshot.speech_active is False
    assert snapshot.reason == ""
    assert snapshot.authority == "NONE"


def test_snapshot_is_frozen():
    snapshot = AvatarSnapshot()

    with pytest.raises(FrozenInstanceError):
        snapshot.reason = "changed"


def test_snapshot_is_slotted():
    assert not hasattr(AvatarSnapshot(), "__dict__")


@pytest.mark.parametrize(
    "mode",
    tuple(mode for mode in AvatarMode if mode != AvatarMode.SPEAKING),
)
def test_non_speaking_modes_accept_false(mode):
    snapshot = AvatarSnapshot(
        mode=mode,
        speech_active=False,
    )

    assert snapshot.mode == mode


def test_speaking_mode_accepts_true():
    snapshot = AvatarSnapshot(
        mode=AvatarMode.SPEAKING,
        speech_active=True,
    )

    assert snapshot.speech_active is True


def test_speaking_mode_rejects_false():
    with pytest.raises(ValueError, match="speech_active"):
        AvatarSnapshot(
            mode=AvatarMode.SPEAKING,
            speech_active=False,
        )


@pytest.mark.parametrize(
    "mode",
    tuple(mode for mode in AvatarMode if mode != AvatarMode.SPEAKING),
)
def test_non_speaking_modes_reject_true(mode):
    with pytest.raises(ValueError, match="speech_active"):
        AvatarSnapshot(
            mode=mode,
            speech_active=True,
        )


def test_mode_requires_enum():
    with pytest.raises(TypeError, match="AvatarMode"):
        AvatarSnapshot(mode="idle")


def test_expression_requires_enum():
    with pytest.raises(TypeError, match="AvatarExpression"):
        AvatarSnapshot(expression="happy")


def test_gaze_requires_enum():
    with pytest.raises(TypeError, match="AvatarGaze"):
        AvatarSnapshot(gaze="user")


@pytest.mark.parametrize("value", (0, 0.0, 0.25, 1, 1.0))
def test_expression_intensity_accepts_bounded_numbers(value):
    snapshot = AvatarSnapshot(
        expression_intensity=value,
    )

    assert snapshot.expression_intensity == float(value)


@pytest.mark.parametrize("value", (0, 0.0, 0.25, 1, 1.0))
def test_motion_energy_accepts_bounded_numbers(value):
    snapshot = AvatarSnapshot(
        motion_energy=value,
    )

    assert snapshot.motion_energy == float(value)


@pytest.mark.parametrize(
    "value",
    (-0.01, 1.01, float("inf"), float("-inf"), float("nan")),
)
def test_expression_intensity_rejects_invalid_numbers(value):
    with pytest.raises(ValueError):
        AvatarSnapshot(expression_intensity=value)


@pytest.mark.parametrize(
    "value",
    (-0.01, 1.01, float("inf"), float("-inf"), float("nan")),
)
def test_motion_energy_rejects_invalid_numbers(value):
    with pytest.raises(ValueError):
        AvatarSnapshot(motion_energy=value)


@pytest.mark.parametrize("value", (True, False, "0.5", None, object()))
def test_expression_intensity_rejects_non_real_values(value):
    with pytest.raises(TypeError):
        AvatarSnapshot(expression_intensity=value)


@pytest.mark.parametrize("value", (True, False, "0.5", None, object()))
def test_motion_energy_rejects_non_real_values(value):
    with pytest.raises(TypeError):
        AvatarSnapshot(motion_energy=value)


def test_speech_active_requires_exact_bool():
    with pytest.raises(TypeError, match="bool"):
        AvatarSnapshot(speech_active=1)


def test_reason_requires_string():
    with pytest.raises(TypeError, match="string"):
        AvatarSnapshot(reason=None)


def test_reason_normalizes_whitespace():
    snapshot = AvatarSnapshot(
        reason="  voice   playback\nstarted  "
    )

    assert snapshot.reason == "voice playback started"


def test_reason_may_be_empty():
    assert AvatarSnapshot(reason="  ").reason == ""


def test_reason_is_bounded():
    with pytest.raises(ValueError, match="bounded"):
        AvatarSnapshot(reason="x" * 513)


def test_reason_accepts_boundary():
    assert len(AvatarSnapshot(reason="x" * 512).reason) == 512


def test_expression_is_independent_of_mode():
    snapshot = AvatarSnapshot(
        mode=AvatarMode.THINKING,
        expression=AvatarExpression.HAPPY,
        expression_intensity=0.5,
    )

    assert snapshot.mode == AvatarMode.THINKING
    assert snapshot.expression == AvatarExpression.HAPPY


@pytest.mark.parametrize(
    "snapshot",
    (
        AvatarSnapshot(
            mode=AvatarMode.ATTENTION,
            expression=AvatarExpression.ALERT,
            expression_intensity=1.0,
            reason="surface event",
        ),
        AvatarSnapshot(
            mode=AvatarMode.ERROR,
            expression=AvatarExpression.ALERT,
            expression_intensity=1.0,
            reason="speech failed",
        ),
        AvatarSnapshot(
            mode=AvatarMode.SUCCESS,
            expression=AvatarExpression.HAPPY,
            expression_intensity=0.75,
        ),
        AvatarSnapshot(
            mode=AvatarMode.SLEEP,
            gaze=AvatarGaze.AWAY,
        ),
        AvatarSnapshot(
            mode=AvatarMode.LISTENING,
            gaze=AvatarGaze.USER,
            motion_energy=0.25,
        ),
        AvatarSnapshot(
            mode=AvatarMode.THINKING,
            expression=AvatarExpression.FOCUSED,
            expression_intensity=0.5,
        ),
        AvatarSnapshot(
            mode=AvatarMode.SPEAKING,
            speech_active=True,
        ),
    ),
)
def test_every_semantic_presentation_remains_zero_authority(snapshot):
    assert snapshot.authority == "NONE"


def test_default_factory_returns_fresh_equal_snapshots():
    first = default_avatar_snapshot()
    second = default_avatar_snapshot()

    assert isinstance(first, AvatarSnapshot)
    assert first == second
    assert first is not second


def test_module_does_not_import_existing_renderer_layers():
    loaded = imports()

    for forbidden in (
        "app.ui.body_state",
        "app.ui.body_controller",
        "app.ui.floating_body",
        "app.ui.avatar",
    ):
        assert forbidden not in loaded


def test_module_does_not_import_qt():
    loaded = imports()

    assert not any(
        name.startswith(("PySide", "PyQt"))
        for name in loaded
    )


def test_module_does_not_import_agent_tools_voice_or_memory():
    loaded = imports()

    assert not any(
        name.startswith(
            (
                "app.agent",
                "app.tools",
                "app.voice",
                "app.memory",
            )
        )
        for name in loaded
    )


def test_module_does_not_import_network_or_models():
    loaded = imports()

    for forbidden in (
        "requests",
        "urllib",
        "httpx",
        "socket",
        "ollama",
        "google.genai",
    ):
        assert forbidden not in loaded


def test_module_does_not_import_background_surfaces():
    loaded = imports()

    for forbidden in (
        "threading",
        "asyncio",
        "subprocess",
    ):
        assert forbidden not in loaded


def test_module_has_no_while_or_async_runtime():
    tree = ast.parse(source(), filename=str(MODULE))

    assert not any(
        isinstance(node, ast.While)
        for node in ast.walk(tree)
    )

    assert not any(
        isinstance(node, ast.AsyncFunctionDef)
        for node in ast.walk(tree)
    )


def test_module_has_no_permission_execution_model_or_persistence_calls():
    names = calls()

    for forbidden in (
        "execute",
        "request_confirmation",
        "get_permission_level",
        "require_explicit_permission",
        "register_tool",
        "ask_model",
        "generate_content",
        "chat",
        "save",
        "write_text",
        "write_bytes",
        "connect",
        "commit",
        "remember",
        "forget",
    ):
        assert forbidden not in names


def test_module_has_no_notification_or_audio_calls():
    names = calls()

    for forbidden in (
        "emit_status",
        "notify",
        "notify_user",
        "speak",
        "play",
        "stop",
    ):
        assert forbidden not in names


def test_module_has_no_qml_or_geometry_literals():
    text = source()

    for forbidden in (
        "KumaMini",
        "bodyState",
        "ear_left",
        "ear_right",
        "hoverOffset",
        "eulerRotation",
        "requestPaint",
    ):
        assert forbidden not in text


def test_contract_documents_core_boundaries():
    text = source()

    for required in (
        "AVATAR STATE != COGNITIVE STATE",
        "AVATAR EXPRESSION != FACT",
        "AVATAR ATTENTION != PERMISSION",
        "SPEAKING != AUTHORITY",
        "ANIMATION != ACTION",
        "PRESENTATION != EXECUTION",
    ):
        assert required in text
