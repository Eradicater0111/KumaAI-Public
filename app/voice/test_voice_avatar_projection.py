from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path

import pytest

from app.ui.avatar_runtime import (
    AvatarExpression,
    AvatarGaze,
    AvatarMode,
    AvatarSnapshot,
)
from app.voice.voice_avatar_projection import (
    project_voice_snapshot_to_avatar,
)
from app.voice.voice_runtime import (
    VoiceInputMode,
    VoiceOutputMode,
    VoiceSnapshot,
    VoiceTranscript,
)


MODULE = Path(
    "app/voice/voice_avatar_projection.py"
)

WINDOW = Path(
    "app/ui/window.py"
)

BODY_CONTROLLER = Path(
    "app/ui/body_controller.py"
)


def voice_snapshot(
    *,
    input_mode=VoiceInputMode.UNAVAILABLE,
    output_mode=VoiceOutputMode.IDLE,
    transcript=None,
    reason="",
):
    return VoiceSnapshot(
        input_mode=input_mode,
        output_mode=output_mode,
        microphone_active=(
            input_mode
            == VoiceInputMode.CAPTURING
        ),
        playback_active=(
            output_mode
            == VoiceOutputMode.PLAYING
        ),
        transcript=transcript,
        reason=reason,
    )


def projection(
    **kwargs,
):
    return (
        project_voice_snapshot_to_avatar(
            voice_snapshot(
                **kwargs
            )
        )
    )


def imports_from_module():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    modules = set()
    symbols = set()

    for node in ast.walk(
        tree
    ):
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            modules.add(
                node.module
            )

            symbols.update(
                alias.name
                for alias in node.names
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias in node.names
            )

            symbols.update(
                alias.name
                for alias in node.names
            )

    return (
        modules,
        symbols,
    )


def function_source():
    text = MODULE.read_text()

    tree = ast.parse(
        text,
        filename=str(MODULE),
    )

    function = next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == "project_voice_snapshot_to_avatar"
        )
    )

    return (
        ast.get_source_segment(
            text,
            function,
        )
        or ""
    )


def test_projection_rejects_non_voice_snapshot():
    with pytest.raises(
        TypeError,
        match="VoiceSnapshot",
    ):
        project_voice_snapshot_to_avatar(
            object()
        )


def test_projection_signature_accepts_only_snapshot():
    signature = inspect.signature(
        project_voice_snapshot_to_avatar
    )

    assert tuple(
        signature.parameters
    ) == (
        "snapshot",
    )


def test_default_voice_state_has_no_avatar_claim():
    assert (
        projection()
        is None
    )


@pytest.mark.parametrize(
    "input_mode",
    (
        VoiceInputMode.UNAVAILABLE,
        VoiceInputMode.INACTIVE,
        VoiceInputMode.ERROR,
        VoiceInputMode.TRANSCRIBING,
    ),
)
def test_non_capturing_input_modes_do_not_claim_listening(
    input_mode,
):
    result = projection(
        input_mode=input_mode
    )

    assert result is None


@pytest.mark.parametrize(
    "output_mode",
    (
        VoiceOutputMode.IDLE,
        VoiceOutputMode.SYNTHESIZING,
        VoiceOutputMode.ERROR,
    ),
)
def test_non_playing_output_modes_do_not_claim_speaking(
    output_mode,
):
    result = projection(
        output_mode=output_mode
    )

    assert result is None


def test_real_capture_truth_projects_listening():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    assert isinstance(
        result,
        AvatarSnapshot,
    )

    assert (
        result.mode
        == AvatarMode.LISTENING
    )


def test_listening_projection_keeps_speech_inactive():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    assert (
        result.speech_active
        is False
    )


def test_listening_projection_uses_user_gaze():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    assert (
        result.gaze
        == AvatarGaze.USER
    )


def test_listening_projection_uses_focused_expression():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    assert (
        result.expression
        == AvatarExpression.FOCUSED
    )


def test_listening_projection_has_bounded_intensity():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    assert (
        0.0
        <= result.expression_intensity
        <= 1.0
    )


def test_listening_projection_has_bounded_motion():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    assert (
        0.0
        <= result.motion_energy
        <= 1.0
    )


def test_listening_projection_reason_is_presentation_fact():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    assert (
        result.reason
        == "microphone capture active"
    )


def test_real_playback_truth_projects_speaking():
    result = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    assert isinstance(
        result,
        AvatarSnapshot,
    )

    assert (
        result.mode
        == AvatarMode.SPEAKING
    )


def test_speaking_projection_sets_speech_active():
    result = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    assert (
        result.speech_active
        is True
    )


def test_speaking_projection_uses_user_gaze():
    result = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    assert (
        result.gaze
        == AvatarGaze.USER
    )


def test_speaking_projection_uses_gentle_expression():
    result = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    assert (
        result.expression
        == AvatarExpression.GENTLE
    )


def test_speaking_projection_has_bounded_intensity():
    result = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    assert (
        0.0
        <= result.expression_intensity
        <= 1.0
    )


def test_speaking_projection_has_bounded_motion():
    result = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    assert (
        0.0
        <= result.motion_energy
        <= 1.0
    )


def test_speaking_projection_reason_is_presentation_fact():
    result = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    assert (
        result.reason
        == "voice playback active"
    )


def test_simultaneous_capture_and_playback_projects_speaking():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        ),
        output_mode=(
            VoiceOutputMode.PLAYING
        ),
    )

    assert (
        result.mode
        == AvatarMode.SPEAKING
    )

    assert (
        result.speech_active
        is True
    )


def test_simultaneous_projection_does_not_mutate_voice_truth():
    source = voice_snapshot(
        input_mode=(
            VoiceInputMode.CAPTURING
        ),
        output_mode=(
            VoiceOutputMode.PLAYING
        ),
    )

    result = (
        project_voice_snapshot_to_avatar(
            source
        )
    )

    assert (
        source.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        source.microphone_active
        is True
    )

    assert (
        source.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert (
        source.playback_active
        is True
    )

    assert (
        result.mode
        == AvatarMode.SPEAKING
    )


def test_playback_precedence_is_presentation_only():
    text = MODULE.read_text()

    assert (
        "PRESENTATION PRECEDENCE != I/O TRUTH LOSS"
        in text
    )


def test_projection_returns_fresh_equal_listening_snapshots():
    source = voice_snapshot(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    first = (
        project_voice_snapshot_to_avatar(
            source
        )
    )

    second = (
        project_voice_snapshot_to_avatar(
            source
        )
    )

    assert first == second
    assert first is not second


def test_projection_returns_fresh_equal_speaking_snapshots():
    source = voice_snapshot(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    first = (
        project_voice_snapshot_to_avatar(
            source
        )
    )

    second = (
        project_voice_snapshot_to_avatar(
            source
        )
    )

    assert first == second
    assert first is not second


def test_projected_snapshot_is_immutable():
    result = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        result.reason = "changed"


@pytest.mark.parametrize(
    (
        "input_mode",
        "output_mode",
    ),
    (
        (
            VoiceInputMode.UNAVAILABLE,
            VoiceOutputMode.IDLE,
        ),
        (
            VoiceInputMode.INACTIVE,
            VoiceOutputMode.SYNTHESIZING,
        ),
        (
            VoiceInputMode.ERROR,
            VoiceOutputMode.IDLE,
        ),
        (
            VoiceInputMode.TRANSCRIBING,
            VoiceOutputMode.ERROR,
        ),
    ),
)
def test_inactive_voice_combinations_make_no_avatar_claim(
    input_mode,
    output_mode,
):
    assert (
        projection(
            input_mode=input_mode,
            output_mode=output_mode,
        )
        is None
    )


def test_input_error_does_not_fabricate_avatar_error():
    assert (
        projection(
            input_mode=(
                VoiceInputMode.ERROR
            )
        )
        is None
    )


def test_output_error_does_not_fabricate_avatar_error():
    assert (
        projection(
            output_mode=(
                VoiceOutputMode.ERROR
            )
        )
        is None
    )


def test_synthesizing_does_not_fabricate_thinking():
    assert (
        projection(
            output_mode=(
                VoiceOutputMode.SYNTHESIZING
            )
        )
        is None
    )


def test_transcribing_does_not_fabricate_thinking():
    assert (
        projection(
            input_mode=(
                VoiceInputMode.TRANSCRIBING
            )
        )
        is None
    )


def test_inactive_does_not_fabricate_idle_avatar():
    assert (
        projection(
            input_mode=(
                VoiceInputMode.INACTIVE
            )
        )
        is None
    )


def test_unavailable_does_not_fabricate_sleep_avatar():
    assert (
        projection(
            input_mode=(
                VoiceInputMode.UNAVAILABLE
            )
        )
        is None
    )


def test_source_reason_does_not_change_listening_semantics():
    first = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        ),
        reason="first source reason",
    )

    second = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        ),
        reason="different source reason",
    )

    assert first == second


def test_source_reason_does_not_change_speaking_semantics():
    first = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        ),
        reason="first source reason",
    )

    second = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        ),
        reason="different source reason",
    )

    assert first == second


def test_transcript_does_not_change_listening_semantics():
    without = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        )
    )

    with_transcript = projection(
        input_mode=(
            VoiceInputMode.CAPTURING
        ),
        transcript=VoiceTranscript(
            "hello"
        ),
    )

    assert without == with_transcript


def test_transcript_does_not_change_speaking_semantics():
    without = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        )
    )

    with_transcript = projection(
        output_mode=(
            VoiceOutputMode.PLAYING
        ),
        transcript=VoiceTranscript(
            "hello"
        ),
    )

    assert without == with_transcript


def test_projection_never_returns_success():
    for source in (
        voice_snapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            )
        ),
        voice_snapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            )
        ),
    ):
        result = (
            project_voice_snapshot_to_avatar(
                source
            )
        )

        assert (
            result.mode
            != AvatarMode.SUCCESS
        )


def test_projection_never_returns_error():
    for source in (
        voice_snapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            )
        ),
        voice_snapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            )
        ),
    ):
        result = (
            project_voice_snapshot_to_avatar(
                source
            )
        )

        assert (
            result.mode
            != AvatarMode.ERROR
        )


def test_projection_never_returns_thinking():
    for source in (
        voice_snapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            )
        ),
        voice_snapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            )
        ),
    ):
        result = (
            project_voice_snapshot_to_avatar(
                source
            )
        )

        assert (
            result.mode
            != AvatarMode.THINKING
        )


def test_projection_never_returns_attention():
    for source in (
        voice_snapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            )
        ),
        voice_snapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            )
        ),
    ):
        result = (
            project_voice_snapshot_to_avatar(
                source
            )
        )

        assert (
            result.mode
            != AvatarMode.ATTENTION
        )


def test_projection_never_returns_sleep():
    for source in (
        voice_snapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            )
        ),
        voice_snapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            )
        ),
    ):
        result = (
            project_voice_snapshot_to_avatar(
                source
            )
        )

        assert (
            result.mode
            != AvatarMode.SLEEP
        )


def test_every_projected_snapshot_has_none_authority():
    for source in (
        voice_snapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            )
        ),
        voice_snapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            )
        ),
        voice_snapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            ),
            output_mode=(
                VoiceOutputMode.PLAYING
            ),
        ),
    ):
        result = (
            project_voice_snapshot_to_avatar(
                source
            )
        )

        assert (
            result.authority
            == "NONE"
        )


def test_projection_has_no_authority_parameter():
    signature = inspect.signature(
        project_voice_snapshot_to_avatar
    )

    assert (
        "authority"
        not in signature.parameters
    )


def test_projection_has_no_permission_parameter():
    signature = inspect.signature(
        project_voice_snapshot_to_avatar
    )

    assert (
        "permission"
        not in signature.parameters
    )


def test_projection_has_no_executor_parameter():
    signature = inspect.signature(
        project_voice_snapshot_to_avatar
    )

    assert (
        "executor"
        not in signature.parameters
    )


def test_projection_function_checks_playback_before_microphone():
    source = function_source()

    playback_index = source.index(
        "if playback_active:"
    )

    microphone_index = source.index(
        "if microphone_active:"
    )

    assert (
        playback_index
        < microphone_index
    )


def test_projection_function_requires_playing_and_playback_flag():
    source = function_source()

    assert (
        "snapshot.output_mode"
        in source
    )

    assert (
        "VoiceOutputMode.PLAYING"
        in source
    )

    assert (
        "snapshot.playback_active"
        in source
    )


def test_projection_function_requires_capturing_and_microphone_flag():
    source = function_source()

    assert (
        "snapshot.input_mode"
        in source
    )

    assert (
        "VoiceInputMode.CAPTURING"
        in source
    )

    assert (
        "snapshot.microphone_active"
        in source
    )


def test_projection_function_has_explicit_none_terminal():
    source = function_source()

    assert (
        source.rstrip().endswith(
            "return None"
        )
    )


def test_module_imports_only_avatar_runtime_from_ui():
    modules, _ = imports_from_module()

    ui_modules = {
        module
        for module in modules
        if module.startswith(
            "app.ui"
        )
    }

    assert ui_modules == {
        "app.ui.avatar_runtime"
    }


def test_module_does_not_import_renderer_or_body_controller():
    modules, _ = imports_from_module()

    for forbidden in (
        "app.ui.avatar_renderer_adapter",
        "app.ui.body_controller",
        "app.ui.floating_body",
        "app.ui.kuma_3d_view",
        "app.ui.window",
    ):
        assert forbidden not in modules


def test_module_does_not_import_voice_io_controllers():
    modules, _ = imports_from_module()

    for forbidden in (
        "app.voice.speech_controller",
        "app.voice.microphone_capture",
        "app.voice.voice_state_bridge",
    ):
        assert forbidden not in modules


def test_module_does_not_import_qt():
    modules, _ = imports_from_module()

    assert not any(
        module.startswith(
            (
                "PySide",
                "PyQt",
            )
        )
        for module in modules
    )


def test_module_has_no_agent_memory_tool_imports():
    modules, _ = imports_from_module()

    for prefix in (
        "app.agent",
        "app.memory",
        "app.tools",
    ):
        assert not any(
            module.startswith(
                prefix
            )
            for module in modules
        )


def test_module_has_no_network_imports():
    modules, _ = imports_from_module()

    forbidden_roots = {
        "requests",
        "httpx",
        "urllib",
        "socket",
        "aiohttp",
        "websockets",
    }

    roots = {
        module.split(
            ".",
            1,
        )[0]
        for module in modules
    }

    assert roots.isdisjoint(
        forbidden_roots
    )


def test_module_has_no_stt_provider_imports():
    modules, _ = imports_from_module()

    for forbidden in (
        "speech_recognition",
        "whisper",
        "faster_whisper",
        "mlx_whisper",
    ):
        assert forbidden not in modules


def test_module_has_no_capture_or_playback_calls():
    source = function_source()

    for forbidden in (
        "start_capture(",
        "stop_capture(",
        "probe_availability(",
        ".speak(",
        ".stop(",
        "QAudioSource",
        "QProcess",
    ):
        assert forbidden not in source


def test_module_has_no_persistence_surface():
    modules, _ = imports_from_module()

    for forbidden in (
        "pathlib",
        "sqlite3",
        "tempfile",
    ):
        assert forbidden not in modules


def test_module_has_no_background_runtime_surface():
    modules, _ = imports_from_module()

    for forbidden in (
        "threading",
        "asyncio",
    ):
        assert forbidden not in modules

    text = MODULE.read_text()

    for forbidden in (
        "QThread",
        "QTimer",
        "while True",
    ):
        assert forbidden not in text


def test_module_has_no_signal_or_mutable_controller():
    text = MODULE.read_text()

    assert (
        "Signal("
        not in text
    )

    assert (
        "QObject"
        not in text
    )


def test_module_defines_no_class():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    assert not any(
        isinstance(
            node,
            ast.ClassDef,
        )
        for node in tree.body
    )


def test_module_defines_exact_projection_function():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    functions = [
        node.name
        for node in tree.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
    ]

    assert functions == [
        "project_voice_snapshot_to_avatar"
    ]


def test_window_does_not_wire_voice_1e_projection_yet():
    text = WINDOW.read_text()

    assert (
        "project_voice_snapshot_to_avatar"
        not in text
    )

    assert (
        "voice_avatar_projection"
        not in text
    )


def test_body_controller_does_not_wire_voice_1e_projection():
    text = BODY_CONTROLLER.read_text()

    assert (
        "project_voice_snapshot_to_avatar"
        not in text
    )

    assert (
        "voice_avatar_projection"
        not in text
    )


def test_voice_1e_does_not_create_live_listening_source_in_window():
    text = WINDOW.read_text()

    assert (
        "AvatarMode.LISTENING"
        not in text
    )


def test_voice_1e_preserves_existing_live_speaking_window_path():
    text = WINDOW.read_text()

    assert (
        "AvatarMode.SPEAKING"
        in text
    )

    assert (
        "speech_active=True"
        in text
    )


def test_module_documents_truth_boundaries():
    text = MODULE.read_text()

    for required in (
        "VOICE SNAPSHOT != AVATAR AUTHORITY",
        "VOICE PRESENTATION != COGNITION",
        "MICROPHONE CAPTURE != COMMAND",
        "PLAYBACK != MODEL CONTROL",
        "LISTENING PRESENTATION REQUIRES REAL CAPTURE TRUTH",
        "SPEAKING PRESENTATION REQUIRES REAL PLAYBACK TRUTH",
        "VOICE-AVATAR PROJECTION AUTHORITY = NONE",
    ):
        assert required in text


def test_module_documents_single_mode_precedence_caveat():
    text = MODULE.read_text()

    assert (
        "The avatar has one semantic mode"
        in text
    )

    assert (
        "SPEAKING receives"
        in text
    )

    assert (
        "VoiceSnapshot remains"
        in text
    )


def test_module_documents_no_idle_or_error_fabrication():
    text = MODULE.read_text()

    assert (
        "does not fabricate IDLE, THINKING, SUCCESS, ERROR"
        in text
    )


def test_projection_module_compiles_as_plain_python_source():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
