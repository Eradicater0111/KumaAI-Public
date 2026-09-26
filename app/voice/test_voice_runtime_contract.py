from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
import ast
import inspect
from pathlib import Path

import pytest

from app.voice.voice_runtime import (
    VOICE_AUTHORITY_NONE,
    VOICE_REASON_MAX_CHARS,
    VOICE_TRANSCRIPT_MAX_CHARS,
    VoiceInputMode,
    VoiceOutputMode,
    VoiceSnapshot,
    VoiceTranscript,
    idle_voice_snapshot,
)


MODULE = Path(
    "app/voice/voice_runtime.py"
)


def module_source():
    return MODULE.read_text()


def parsed_module():
    return ast.parse(
        module_source(),
        filename=str(MODULE),
    )


def test_authority_constant_is_none():
    assert (
        VOICE_AUTHORITY_NONE
        == "NONE"
    )


def test_input_mode_surface_is_exact():
    assert tuple(
        VoiceInputMode
    ) == (
        VoiceInputMode.UNAVAILABLE,
        VoiceInputMode.INACTIVE,
        VoiceInputMode.CAPTURING,
        VoiceInputMode.TRANSCRIBING,
        VoiceInputMode.ERROR,
    )


def test_output_mode_surface_is_exact():
    assert tuple(
        VoiceOutputMode
    ) == (
        VoiceOutputMode.IDLE,
        VoiceOutputMode.SYNTHESIZING,
        VoiceOutputMode.PLAYING,
        VoiceOutputMode.ERROR,
    )


def test_transcript_fields_are_exact():
    assert tuple(
        item.name
        for item in fields(
            VoiceTranscript
        )
    ) == (
        "text",
        "is_final",
        "authority",
    )


def test_snapshot_fields_are_exact():
    assert tuple(
        item.name
        for item in fields(
            VoiceSnapshot
        )
    ) == (
        "input_mode",
        "output_mode",
        "microphone_active",
        "playback_active",
        "transcript",
        "reason",
        "authority",
    )


def test_transcript_is_frozen():
    value = VoiceTranscript(
        "hello"
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        value.text = "changed"


def test_snapshot_is_frozen():
    value = VoiceSnapshot()

    with pytest.raises(
        FrozenInstanceError
    ):
        value.reason = "changed"


def test_transcript_is_slotted():
    assert (
        "__dict__"
        not in dir(
            VoiceTranscript(
                "hello"
            )
        )
    )


def test_snapshot_is_slotted():
    assert (
        "__dict__"
        not in dir(
            VoiceSnapshot()
        )
    )


def test_transcript_authority_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            VoiceTranscript
        ).parameters
    )


def test_snapshot_authority_not_constructor_input():
    assert (
        "authority"
        not in inspect.signature(
            VoiceSnapshot
        ).parameters
    )


def test_default_snapshot_does_not_fabricate_microphone():
    value = VoiceSnapshot()

    assert (
        value.input_mode
        == VoiceInputMode.UNAVAILABLE
    )
    assert (
        value.microphone_active
        is False
    )


def test_default_snapshot_has_idle_output():
    value = VoiceSnapshot()

    assert (
        value.output_mode
        == VoiceOutputMode.IDLE
    )
    assert (
        value.playback_active
        is False
    )


def test_default_snapshot_has_no_transcript():
    assert (
        VoiceSnapshot().transcript
        is None
    )


def test_default_snapshot_authority_is_none():
    assert (
        VoiceSnapshot().authority
        == "NONE"
    )


def test_default_transcript_authority_is_none():
    assert (
        VoiceTranscript(
            "hello"
        ).authority
        == "NONE"
    )


@pytest.mark.parametrize(
    "mode",
    tuple(
        VoiceInputMode
    ),
)
def test_input_modes_require_matching_microphone_truth(
    mode,
):
    active = (
        mode
        == VoiceInputMode.CAPTURING
    )

    snapshot = VoiceSnapshot(
        input_mode=mode,
        microphone_active=active,
    )

    assert (
        snapshot.microphone_active
        is active
    )


@pytest.mark.parametrize(
    "mode",
    tuple(
        VoiceOutputMode
    ),
)
def test_output_modes_require_matching_playback_truth(
    mode,
):
    active = (
        mode
        == VoiceOutputMode.PLAYING
    )

    snapshot = VoiceSnapshot(
        output_mode=mode,
        playback_active=active,
    )

    assert (
        snapshot.playback_active
        is active
    )


@pytest.mark.parametrize(
    "mode",
    tuple(
        value
        for value in VoiceInputMode
        if value
        != VoiceInputMode.CAPTURING
    ),
)
def test_non_capturing_modes_reject_active_microphone(
    mode,
):
    with pytest.raises(
        ValueError,
        match="microphone_active",
    ):
        VoiceSnapshot(
            input_mode=mode,
            microphone_active=True,
        )


def test_capturing_rejects_inactive_microphone_flag():
    with pytest.raises(
        ValueError,
        match="microphone_active",
    ):
        VoiceSnapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            ),
            microphone_active=False,
        )


@pytest.mark.parametrize(
    "mode",
    tuple(
        value
        for value in VoiceOutputMode
        if value
        != VoiceOutputMode.PLAYING
    ),
)
def test_non_playing_modes_reject_active_playback(
    mode,
):
    with pytest.raises(
        ValueError,
        match="playback_active",
    ):
        VoiceSnapshot(
            output_mode=mode,
            playback_active=True,
        )


def test_playing_rejects_inactive_playback_flag():
    with pytest.raises(
        ValueError,
        match="playback_active",
    ):
        VoiceSnapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            ),
            playback_active=False,
        )


@pytest.mark.parametrize(
    (
        "field_name",
        "value",
    ),
    (
        (
            "microphone_active",
            1,
        ),
        (
            "microphone_active",
            "true",
        ),
        (
            "playback_active",
            1,
        ),
        (
            "playback_active",
            "true",
        ),
    ),
)
def test_io_truth_flags_require_exact_bool(
    field_name,
    value,
):
    kwargs = {
        field_name: value,
    }

    with pytest.raises(
        TypeError,
        match=field_name,
    ):
        VoiceSnapshot(
            **kwargs
        )


def test_input_mode_requires_enum():
    with pytest.raises(
        TypeError,
        match="input_mode",
    ):
        VoiceSnapshot(
            input_mode="capturing"
        )


def test_output_mode_requires_enum():
    with pytest.raises(
        TypeError,
        match="output_mode",
    ):
        VoiceSnapshot(
            output_mode="playing"
        )


def test_transcript_requires_string():
    with pytest.raises(
        TypeError,
        match="text",
    ):
        VoiceTranscript(
            123
        )


def test_transcript_requires_exact_bool_for_finality():
    with pytest.raises(
        TypeError,
        match="is_final",
    ):
        VoiceTranscript(
            "hello",
            is_final=1,
        )


def test_transcript_normalizes_whitespace():
    value = VoiceTranscript(
        "  hello\n   there  "
    )

    assert (
        value.text
        == "hello there"
    )


@pytest.mark.parametrize(
    "value",
    (
        "",
        " ",
        "\n\t",
    ),
)
def test_transcript_rejects_empty_text(
    value,
):
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        VoiceTranscript(
            value
        )


def test_transcript_accepts_boundary_length():
    value = VoiceTranscript(
        "x"
        * VOICE_TRANSCRIPT_MAX_CHARS
    )

    assert (
        len(
            value.text
        )
        == VOICE_TRANSCRIPT_MAX_CHARS
    )


def test_transcript_rejects_over_boundary():
    with pytest.raises(
        ValueError,
        match="characters",
    ):
        VoiceTranscript(
            "x"
            * (
                VOICE_TRANSCRIPT_MAX_CHARS
                + 1
            )
        )


def test_reason_normalizes_whitespace():
    value = VoiceSnapshot(
        reason=(
            "  microphone\n"
            " unavailable  "
        )
    )

    assert (
        value.reason
        == "microphone unavailable"
    )


def test_reason_accepts_empty():
    assert (
        VoiceSnapshot(
            reason=""
        ).reason
        == ""
    )


def test_reason_accepts_boundary_length():
    value = VoiceSnapshot(
        reason=(
            "x"
            * VOICE_REASON_MAX_CHARS
        )
    )

    assert (
        len(
            value.reason
        )
        == VOICE_REASON_MAX_CHARS
    )


def test_reason_rejects_over_boundary():
    with pytest.raises(
        ValueError,
        match="characters",
    ):
        VoiceSnapshot(
            reason=(
                "x"
                * (
                    VOICE_REASON_MAX_CHARS
                    + 1
                )
            )
        )


def test_reason_requires_string():
    with pytest.raises(
        TypeError,
        match="reason",
    ):
        VoiceSnapshot(
            reason=123
        )


def test_snapshot_rejects_non_transcript():
    with pytest.raises(
        TypeError,
        match="transcript",
    ):
        VoiceSnapshot(
            transcript="hello"
        )


def test_snapshot_accepts_zero_authority_transcript():
    transcript = VoiceTranscript(
        "hello"
    )

    snapshot = VoiceSnapshot(
        transcript=transcript
    )

    assert (
        snapshot.transcript
        is transcript
    )

    assert (
        snapshot.transcript.authority
        == "NONE"
    )

    assert (
        snapshot.authority
        == "NONE"
    )


def test_transcript_may_be_partial():
    value = VoiceTranscript(
        "hel",
        is_final=False,
    )

    assert (
        value.is_final
        is False
    )


def test_transcript_may_be_final():
    value = VoiceTranscript(
        "hello",
        is_final=True,
    )

    assert (
        value.is_final
        is True
    )


def test_idle_factory_returns_fresh_equal_snapshots():
    first = idle_voice_snapshot()
    second = idle_voice_snapshot()

    assert (
        first
        == second
    )

    assert (
        first
        is not second
    )


def test_idle_factory_signature_has_no_inputs():
    assert (
        tuple(
            inspect.signature(
                idle_voice_snapshot
            ).parameters
        )
        == ()
    )


def test_contract_documents_core_boundaries():
    text = module_source()

    for required in (
        "VOICE STATE != COGNITIVE STATE",
        "TRANSCRIPT != COMMAND AUTHORITY",
        "MICROPHONE ACTIVE != LISTENING ANIMATION",
        "LISTENING ANIMATION MUST FOLLOW REAL CAPTURE STATE",
        "PLAYBACK ACTIVE MUST FOLLOW REAL AUDIO PLAYBACK",
        "TTS OUTPUT != MODEL CONTROL",
        "VOICE ERROR != TASK FAILURE",
        "VOICE INPUT != PERMISSION",
        "VOICE != EXECUTION",
        "VOICE AUTHORITY = NONE",
    ):
        assert required in text


def test_module_has_no_qt_dependency():
    text = module_source()

    assert (
        "PySide"
        not in text
    )
    assert (
        "PyQt"
        not in text
    )
    assert (
        "QProcess"
        not in text
    )
    assert (
        "QTimer"
        not in text
    )


def test_module_has_no_agent_tool_memory_dependency():
    tree = parsed_module()

    modules = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        ):
            modules.add(
                node.module
            )

    for prefix in (
        "app.agent",
        "app.tools",
        "app.memory",
        "app.ui",
    ):
        assert not any(
            module.startswith(
                prefix
            )
            for module in modules
        )


def test_module_has_no_network_or_provider_dependency():
    text = module_source()

    for forbidden in (
        "requests",
        "aiohttp",
        "websocket",
        "socket",
        "OpenAI",
        "ElevenLabs",
        "Azure",
        "Polly",
        "Kokoro",
        "mlx",
        "http://",
        "https://",
    ):
        assert forbidden not in text


def test_module_has_no_audio_io_calls():
    text = module_source()

    for forbidden in (
        "microphone.open",
        "record(",
        "capture(",
        "play(",
        "speak(",
        "save(",
        "transcribe(",
        "recognize(",
    ):
        assert forbidden not in text


def test_module_has_no_permission_execution_surface():
    text = module_source()

    for forbidden in (
        "request_confirmation",
        "confirm_dangerous_action",
        "permission_level",
        "execute_command",
        "executor",
        "tool_registry",
        "pending_signals",
        "TaskState",
        "GoalStatus",
        "mark_finished",
        "record_failure",
    ):
        assert forbidden not in text


def test_module_has_no_background_runtime():
    tree = parsed_module()

    assert not any(
        isinstance(
            node,
            (
                ast.While,
                ast.AsyncFunctionDef,
            ),
        )
        for node in ast.walk(
            tree
        )
    )


def test_module_import_surface_is_stdlib_only():
    tree = parsed_module()

    imports = set()

    for node in tree.body:
        if isinstance(
            node,
            ast.Import,
        ):
            imports.update(
                alias.name
                for alias in node.names
            )

        elif (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
            and node.module
            != "__future__"
        ):
            imports.add(
                node.module
            )

    assert imports == {
        "dataclasses",
        "enum",
        "re",
    }


def test_contract_does_not_import_existing_speech_controller():
    assert (
        "speech_controller"
        not in module_source()
    )


def test_contract_does_not_import_neural_tts_worker():
    assert (
        "neural_tts_worker"
        not in module_source()
    )


def test_contract_does_not_claim_microphone_exists():
    snapshot = idle_voice_snapshot()

    assert (
        snapshot.input_mode
        == VoiceInputMode.UNAVAILABLE
    )

    assert (
        snapshot.microphone_active
        is False
    )


def test_capturing_snapshot_represents_real_capture_truth_only():
    snapshot = VoiceSnapshot(
        input_mode=(
            VoiceInputMode.CAPTURING
        ),
        microphone_active=True,
    )

    assert (
        snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        snapshot.microphone_active
        is True
    )

    assert (
        snapshot.authority
        == "NONE"
    )


def test_playing_snapshot_represents_real_playback_truth_only():
    snapshot = VoiceSnapshot(
        output_mode=(
            VoiceOutputMode.PLAYING
        ),
        playback_active=True,
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert (
        snapshot.playback_active
        is True
    )

    assert (
        snapshot.authority
        == "NONE"
    )


def test_error_modes_do_not_imply_task_failure_authority():
    snapshot = VoiceSnapshot(
        input_mode=VoiceInputMode.ERROR,
        output_mode=VoiceOutputMode.ERROR,
        reason="voice io failed",
    )

    assert (
        snapshot.authority
        == "NONE"
    )

    assert (
        snapshot.microphone_active
        is False
    )

    assert (
        snapshot.playback_active
        is False
    )


def test_transcript_does_not_expose_authority_input():
    signature = inspect.signature(
        VoiceTranscript
    )

    assert (
        "authority"
        not in signature.parameters
    )

    assert (
        "permission"
        not in signature.parameters
    )

    assert (
        "execute"
        not in signature.parameters
    )


def test_snapshot_does_not_expose_authority_input():
    signature = inspect.signature(
        VoiceSnapshot
    )

    for forbidden in (
        "authority",
        "permission",
        "execute",
        "command",
        "tool",
    ):
        assert (
            forbidden
            not in signature.parameters
        )
