from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.voice.speech_controller import (
    KumaSpeechController,
)
from app.voice.voice_runtime import (
    VoiceInputMode,
    VoiceOutputMode,
    VoiceSnapshot,
    VoiceTranscript,
    idle_voice_snapshot,
)


CONTROLLER = Path(
    "app/voice/speech_controller.py"
)

RUNTIME = Path(
    "app/voice/voice_runtime.py"
)

WINDOW = Path(
    "app/ui/window.py"
)


def source(path):
    return path.read_text()


def parsed(path):
    return ast.parse(
        source(path),
        filename=str(path),
    )


def method_source(
    name,
):
    text = source(
        CONTROLLER
    )

    tree = ast.parse(
        text,
        filename=str(CONTROLLER),
    )

    cls = next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.ClassDef,
            )
            and node.name
            == "KumaSpeechController"
        )
    )

    method = next(
        node
        for node in cls.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == name
        )
    )

    return (
        ast.get_source_segment(
            text,
            method,
        )
        or ""
    )


@pytest.fixture
def controller(
    monkeypatch,
):
    monkeypatch.setenv(
        "KUMA_TTS_ENABLED",
        "0",
    )

    return KumaSpeechController()


def collect_voice_states(
    controller,
):
    states = []

    controller.voice_state_changed.connect(
        states.append
    )

    return states


def test_controller_declares_voice_state_changed_signal():
    text = source(
        CONTROLLER
    )

    assert (
        "voice_state_changed = Signal(object)"
        in text
    )


def test_controller_imports_frozen_voice_runtime_contract():
    text = source(
        CONTROLLER
    )

    assert (
        "from app.voice.voice_runtime import ("
        in text
    )

    for required in (
        "VoiceOutputMode",
        "VoiceSnapshot",
        "idle_voice_snapshot",
    ):
        assert required in text


def test_controller_initial_snapshot_is_idle(
    controller,
):
    assert (
        controller.voice_snapshot
        == idle_voice_snapshot()
    )


def test_initial_snapshot_does_not_fabricate_microphone(
    controller,
):
    snapshot = (
        controller.voice_snapshot
    )

    assert (
        snapshot.input_mode
        == VoiceInputMode.UNAVAILABLE
    )

    assert (
        snapshot.microphone_active
        is False
    )


def test_initial_snapshot_does_not_fabricate_playback(
    controller,
):
    snapshot = (
        controller.voice_snapshot
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.IDLE
    )

    assert (
        snapshot.playback_active
        is False
    )


def test_voice_snapshot_property_has_no_setter():
    descriptor = (
        KumaSpeechController
        .voice_snapshot
    )

    assert isinstance(
        descriptor,
        property,
    )

    assert (
        descriptor.fset
        is None
    )


def test_voice_snapshot_property_returns_immutable_contract(
    controller,
):
    assert isinstance(
        controller.voice_snapshot,
        VoiceSnapshot,
    )

    assert (
        controller.voice_snapshot.authority
        == "NONE"
    )


@pytest.mark.parametrize(
    (
        "mode",
        "active",
    ),
    (
        (
            VoiceOutputMode.IDLE,
            False,
        ),
        (
            VoiceOutputMode.SYNTHESIZING,
            False,
        ),
        (
            VoiceOutputMode.PLAYING,
            True,
        ),
        (
            VoiceOutputMode.ERROR,
            False,
        ),
    ),
)
def test_publish_output_state_obeys_playback_truth(
    controller,
    mode,
    active,
):
    snapshot = (
        controller
        ._publish_output_state(
            mode,
            reason="test",
        )
    )

    assert (
        snapshot.output_mode
        == mode
    )

    assert (
        snapshot.playback_active
        is active
    )

    assert (
        snapshot.authority
        == "NONE"
    )


def test_publish_output_state_emits_snapshot(
    controller,
):
    states = collect_voice_states(
        controller
    )

    result = (
        controller
        ._publish_output_state(
            VoiceOutputMode.SYNTHESIZING,
            reason="speech output accepted",
        )
    )

    assert states == [
        result
    ]

    assert (
        states[0]
        is controller.voice_snapshot
    )


def test_publish_output_state_rejects_non_enum(
    controller,
):
    with pytest.raises(
        TypeError,
        match="VoiceOutputMode",
    ):
        controller._publish_output_state(
            "playing",
            reason="bad",
        )


def test_output_transition_preserves_input_side_truth(
    controller,
):
    transcript = VoiceTranscript(
        "hello",
        is_final=False,
    )

    controller._voice_snapshot = (
        VoiceSnapshot(
            input_mode=(
                VoiceInputMode.CAPTURING
            ),
            microphone_active=True,
            transcript=transcript,
            reason="capturing",
        )
    )

    result = (
        controller
        ._publish_output_state(
            VoiceOutputMode.PLAYING,
            reason="playback started",
        )
    )

    assert (
        result.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        result.microphone_active
        is True
    )

    assert (
        result.transcript
        is transcript
    )

    assert (
        result.playback_active
        is True
    )


def test_output_transition_never_changes_authority(
    controller,
):
    for mode in VoiceOutputMode:
        result = (
            controller
            ._publish_output_state(
                mode,
                reason=mode.value,
            )
        )

        assert (
            result.authority
            == "NONE"
        )


def test_disabled_speak_does_not_publish_output_state(
    controller,
):
    states = collect_voice_states(
        controller
    )

    assert (
        controller.speak(
            "hello"
        )
        is False
    )

    assert states == []

    assert (
        controller.voice_snapshot
        == idle_voice_snapshot()
    )


def test_empty_speak_check_precedes_stop_and_synthesis():
    method = method_source(
        "speak"
    )

    prepared_check = (
        "if not prepared:"
    )

    stop_call = (
        "self.stop()"
    )

    publish_call = (
        "self._publish_output_state("
    )

    assert (
        method.index(
            prepared_check
        )
        < method.index(
            stop_call
        )
        < method.index(
            publish_call
        )
    )


def test_accepted_speak_publishes_synthesizing_not_playing():
    method = method_source(
        "speak"
    )

    assert (
        "VoiceOutputMode.SYNTHESIZING"
        in method
    )

    assert (
        "VoiceOutputMode.PLAYING"
        not in method
    )


def test_accepted_speak_sets_active_text_before_synthesizing():
    method = method_source(
        "speak"
    )

    assert (
        method.index(
            "self._active_text = prepared"
        )
        < method.index(
            "VoiceOutputMode.SYNTHESIZING"
        )
    )


def test_speak_request_does_not_emit_speech_started_directly():
    method = method_source(
        "speak"
    )

    assert (
        "speech_started.emit("
        not in method
    )


def test_speak_request_does_not_claim_playback_active_directly():
    method = method_source(
        "speak"
    )

    assert (
        "playback_active=True"
        not in method
    )


def test_playback_start_helper_is_the_playing_boundary():
    method = method_source(
        "_emit_started_if_current"
    )

    assert (
        "VoiceOutputMode.PLAYING"
        in method
    )

    assert (
        "self.speech_started.emit()"
        in method
    )

    assert (
        method.index(
            "VoiceOutputMode.PLAYING"
        )
        < method.index(
            "self.speech_started.emit()"
        )
    )


def test_stale_playback_start_does_not_publish_state(
    controller,
):
    states = collect_voice_states(
        controller
    )

    controller._publish_output_state(
        VoiceOutputMode.SYNTHESIZING,
        reason="accepted",
    )

    states.clear()

    controller._emit_started_if_current(
        controller._generation
        + 1
    )

    assert states == []

    assert (
        controller.voice_snapshot.output_mode
        == VoiceOutputMode.SYNTHESIZING
    )


def test_current_playback_start_publishes_playing_before_legacy_signal(
    controller,
):
    events = []

    controller.voice_state_changed.connect(
        lambda snapshot:
        events.append(
            (
                "state",
                snapshot.output_mode,
                snapshot.playback_active,
            )
        )
    )

    controller.speech_started.connect(
        lambda:
        events.append(
            (
                "legacy",
                "started",
            )
        )
    )

    controller._publish_output_state(
        VoiceOutputMode.SYNTHESIZING,
        reason="accepted",
    )

    events.clear()

    controller._emit_started_if_current(
        controller._generation
    )

    assert events == [
        (
            "state",
            VoiceOutputMode.PLAYING,
            True,
        ),
        (
            "legacy",
            "started",
        ),
    ]


@pytest.mark.parametrize(
    "method_name",
    (
        "_start_neural_playback",
        "_start_system",
    ),
)
def test_both_real_player_backends_connect_qprocess_started_to_truth_helper(
    method_name,
):
    method = method_source(
        method_name
    )

    assert (
        ".started.connect("
        in method
    )

    assert (
        "self._emit_started_if_current("
        in method
    )

    assert (
        ".start("
        in method
    )

    assert (
        method.index(
            ".started.connect("
        )
        < method.index(
            ".start("
        )
    )


def test_neural_player_launch_does_not_publish_playing_before_qprocess_started():
    method = method_source(
        "_start_neural_playback"
    )

    assert (
        "VoiceOutputMode.PLAYING"
        not in method
    )


def test_system_player_launch_does_not_publish_playing_before_qprocess_started():
    method = method_source(
        "_start_system"
    )

    assert (
        "VoiceOutputMode.PLAYING"
        not in method
    )


def test_neural_success_publishes_idle_before_legacy_finished(
    controller,
):
    events = []

    controller.voice_state_changed.connect(
        lambda snapshot:
        events.append(
            (
                "state",
                snapshot.output_mode,
            )
        )
    )

    controller.speech_finished.connect(
        lambda:
        events.append(
            (
                "legacy",
                "finished",
            )
        )
    )

    controller._publish_output_state(
        VoiceOutputMode.PLAYING,
        reason="playing",
    )

    events.clear()

    controller._on_playback_finished(
        controller._generation,
        0,
        None,
    )

    assert events == [
        (
            "state",
            VoiceOutputMode.IDLE,
        ),
        (
            "legacy",
            "finished",
        ),
    ]


def test_neural_nonzero_exit_publishes_error_before_legacy_error(
    controller,
):
    events = []

    controller.voice_state_changed.connect(
        lambda snapshot:
        events.append(
            (
                "state",
                snapshot.output_mode,
            )
        )
    )

    controller.speech_error.connect(
        lambda message:
        events.append(
            (
                "legacy",
                message,
            )
        )
    )

    controller._publish_output_state(
        VoiceOutputMode.PLAYING,
        reason="playing",
    )

    events.clear()

    controller._on_playback_finished(
        controller._generation,
        1,
        None,
    )

    assert events[0] == (
        "state",
        VoiceOutputMode.ERROR,
    )

    assert events[1][0] == (
        "legacy"
    )


def test_neural_player_error_publishes_error_before_legacy_error(
    controller,
):
    events = []

    controller.voice_state_changed.connect(
        lambda snapshot:
        events.append(
            (
                "state",
                snapshot.output_mode,
            )
        )
    )

    controller.speech_error.connect(
        lambda message:
        events.append(
            (
                "legacy",
                message,
            )
        )
    )

    controller._publish_output_state(
        VoiceOutputMode.PLAYING,
        reason="playing",
    )

    events.clear()

    controller._on_playback_error(
        controller._generation,
        None,
    )

    assert events[0] == (
        "state",
        VoiceOutputMode.ERROR,
    )

    assert events[1][0] == (
        "legacy"
    )


def test_system_success_publishes_idle_before_legacy_finished(
    controller,
):
    events = []

    controller.voice_state_changed.connect(
        lambda snapshot:
        events.append(
            (
                "state",
                snapshot.output_mode,
            )
        )
    )

    controller.speech_finished.connect(
        lambda:
        events.append(
            (
                "legacy",
                "finished",
            )
        )
    )

    controller._publish_output_state(
        VoiceOutputMode.PLAYING,
        reason="playing",
    )

    events.clear()

    controller._on_system_finished(
        controller._generation,
        0,
        None,
    )

    assert events == [
        (
            "state",
            VoiceOutputMode.IDLE,
        ),
        (
            "legacy",
            "finished",
        ),
    ]


def test_system_nonzero_exit_publishes_error_before_legacy_error(
    controller,
):
    events = []

    controller.voice_state_changed.connect(
        lambda snapshot:
        events.append(
            (
                "state",
                snapshot.output_mode,
            )
        )
    )

    controller.speech_error.connect(
        lambda message:
        events.append(
            (
                "legacy",
                message,
            )
        )
    )

    controller._publish_output_state(
        VoiceOutputMode.PLAYING,
        reason="playing",
    )

    events.clear()

    controller._on_system_finished(
        controller._generation,
        1,
        None,
    )

    assert events[0] == (
        "state",
        VoiceOutputMode.ERROR,
    )

    assert events[1][0] == (
        "legacy"
    )


def test_system_process_error_publishes_error_before_legacy_error(
    controller,
):
    events = []

    controller.voice_state_changed.connect(
        lambda snapshot:
        events.append(
            (
                "state",
                snapshot.output_mode,
            )
        )
    )

    controller.speech_error.connect(
        lambda message:
        events.append(
            (
                "legacy",
                message,
            )
        )
    )

    controller._publish_output_state(
        VoiceOutputMode.PLAYING,
        reason="playing",
    )

    events.clear()

    controller._on_system_error(
        controller._generation,
        None,
    )

    assert events[0] == (
        "state",
        VoiceOutputMode.ERROR,
    )

    assert events[1][0] == (
        "legacy"
    )


@pytest.mark.parametrize(
    "method_name",
    (
        "_on_playback_finished",
        "_on_playback_error",
        "_on_system_finished",
        "_on_system_error",
    ),
)
def test_stale_terminal_callback_cannot_change_current_voice_state(
    controller,
    method_name,
):
    controller._publish_output_state(
        VoiceOutputMode.SYNTHESIZING,
        reason="new request",
    )

    before = (
        controller.voice_snapshot
    )

    method = getattr(
        controller,
        method_name,
    )

    stale = (
        controller._generation
        + 1
    )

    if (
        method_name
        in {
            "_on_playback_finished",
            "_on_system_finished",
        }
    ):
        method(
            stale,
            0,
            None,
        )
    else:
        method(
            stale,
            None,
        )

    assert (
        controller.voice_snapshot
        == before
    )


def test_stop_returns_synthesizing_state_to_idle(
    controller,
):
    controller._publish_output_state(
        VoiceOutputMode.SYNTHESIZING,
        reason="accepted",
    )

    controller.stop()

    assert (
        controller.voice_snapshot.output_mode
        == VoiceOutputMode.IDLE
    )

    assert (
        controller.voice_snapshot.playback_active
        is False
    )


def test_stop_returns_playing_state_to_idle(
    controller,
):
    controller._publish_output_state(
        VoiceOutputMode.PLAYING,
        reason="playing",
    )

    controller.stop()

    assert (
        controller.voice_snapshot.output_mode
        == VoiceOutputMode.IDLE
    )

    assert (
        controller.voice_snapshot.playback_active
        is False
    )


def test_idle_stop_does_not_emit_spurious_voice_transition(
    controller,
):
    states = collect_voice_states(
        controller
    )

    controller.stop()

    assert states == []


def test_stop_invalidates_generation_before_terminal_state():
    method = method_source(
        "stop"
    )

    assert (
        method.index(
            "self._generation += 1"
        )
        < method.rindex(
            "VoiceOutputMode.IDLE"
        )
    )


def test_stop_kills_owned_processes_before_idle_publication():
    method = method_source(
        "stop"
    )

    assert (
        "process.kill()"
        in method
    )

    assert (
        method.index(
            "process.kill()"
        )
        < method.rindex(
            "VoiceOutputMode.IDLE"
        )
    )


def test_stop_clears_owned_process_references_before_idle_publication():
    method = method_source(
        "stop"
    )

    assert (
        method.index(
            "self._player = None"
        )
        < method.rindex(
            "VoiceOutputMode.IDLE"
        )
    )

    assert (
        method.index(
            "self._system_process = None"
        )
        < method.rindex(
            "VoiceOutputMode.IDLE"
        )
    )


def test_stop_cleanup_happens_before_idle_publication():
    method = method_source(
        "stop"
    )

    assert (
        method.index(
            "self._cleanup_active_audio()"
        )
        < method.rindex(
            "VoiceOutputMode.IDLE"
        )
    )


def test_neural_generation_fallback_does_not_claim_playing():
    method = method_source(
        "_handle_neural_error_event"
    )

    assert (
        "VoiceOutputMode.PLAYING"
        not in method
    )

    assert (
        "self._start_system("
        in method
    )


def test_missing_neural_audio_fallback_does_not_claim_playing():
    method = method_source(
        "_handle_generated_event"
    )

    marker = (
        'self._fallback_current_text('
    )

    assert marker in method

    before_fallback = method[
        :method.index(
            marker
        )
    ]

    assert (
        "VoiceOutputMode.PLAYING"
        not in before_fallback
    )


def test_generation_submission_does_not_claim_playback():
    method = method_source(
        "_submit_neural_request"
    )

    assert (
        "VoiceOutputMode.PLAYING"
        not in method
    )

    assert (
        "speech_started.emit("
        not in method
    )


def test_voice_output_adapter_has_no_microphone_transition():
    text = source(
        CONTROLLER
    )

    adapter_methods = "\n".join(
        method_source(
            name
        )
        for name in (
            "_publish_output_state",
            "_emit_started_if_current",
            "_on_playback_finished",
            "_on_playback_error",
            "_on_system_finished",
            "_on_system_error",
        )
    )

    assert (
        "VoiceInputMode.CAPTURING"
        not in adapter_methods
    )

    assert (
        "microphone_active=True"
        not in adapter_methods
    )


def test_voice_output_adapter_preserves_existing_transcript():
    method = method_source(
        "_publish_output_state"
    )

    assert (
        "transcript=current.transcript"
        in method
    )


def test_voice_output_adapter_preserves_existing_input_mode():
    method = method_source(
        "_publish_output_state"
    )

    tree = ast.parse(
        method
    )

    snapshot_call = next(
        node
        for node in ast.walk(
            tree
        )
        if (
            isinstance(
                node,
                ast.Call,
            )
            and isinstance(
                node.func,
                ast.Name,
            )
            and node.func.id
            == "VoiceSnapshot"
        )
    )

    keywords = {
        item.arg: item.value
        for item in snapshot_call.keywords
        if item.arg is not None
    }

    input_mode = keywords[
        "input_mode"
    ]

    microphone_active = keywords[
        "microphone_active"
    ]

    assert isinstance(
        input_mode,
        ast.Attribute,
    )

    assert isinstance(
        input_mode.value,
        ast.Name,
    )

    assert (
        input_mode.value.id
        == "current"
    )

    assert (
        input_mode.attr
        == "input_mode"
    )

    assert isinstance(
        microphone_active,
        ast.Attribute,
    )

    assert isinstance(
        microphone_active.value,
        ast.Name,
    )

    assert (
        microphone_active.value.id
        == "current"
    )

    assert (
        microphone_active.attr
        == "microphone_active"
    )


def test_voice_output_adapter_derives_playback_flag_only_from_playing_mode():
    method = method_source(
        "_publish_output_state"
    )

    compact = "".join(
        method.split()
    )

    assert (
        "mode==VoiceOutputMode.PLAYING"
        in compact
    )


def test_voice_output_adapter_does_not_accept_playback_flag_input():
    signature = inspect.signature(
        KumaSpeechController
        ._publish_output_state
    )

    assert (
        "playback_active"
        not in signature.parameters
    )


def test_voice_output_adapter_does_not_accept_authority_input():
    signature = inspect.signature(
        KumaSpeechController
        ._publish_output_state
    )

    assert (
        "authority"
        not in signature.parameters
    )


def test_voice_output_adapter_does_not_accept_transcript_input():
    signature = inspect.signature(
        KumaSpeechController
        ._publish_output_state
    )

    assert (
        "transcript"
        not in signature.parameters
    )


def test_voice_output_adapter_contains_no_agent_tool_memory_authority_calls():
    method = method_source(
        "_publish_output_state"
    )

    for forbidden in (
        "request_confirmation",
        "execute_command",
        "executor",
        "tool_registry",
        "pending_signals",
        "TaskState",
        "GoalStatus",
        "memory",
    ):
        assert (
            forbidden
            not in method
        ), forbidden


def test_existing_legacy_signal_surface_is_preserved():
    text = source(
        CONTROLLER
    )

    for required in (
        "speech_started = Signal()",
        "speech_finished = Signal()",
        "speech_error = Signal(str)",
        "voice_ready = Signal()",
    ):
        assert required in text


def test_window_does_not_need_voice_1b_modification():
    text = source(
        WINDOW
    )

    assert (
        "voice_state_changed"
        not in text
    )

    assert (
        "VoiceOutputMode"
        not in text
    )


def test_existing_avatar_speaking_bridge_still_consumes_legacy_started_signal():
    text = source(
        WINDOW
    )

    assert (
        "self.speech.speech_started.connect("
        in text
    )

    assert (
        "self._on_kuma_speech_started"
        in text
    )


def test_existing_avatar_finished_bridge_still_consumes_legacy_finished_signal():
    text = source(
        WINDOW
    )

    assert (
        "self.speech.speech_finished.connect("
        in text
    )

    assert (
        "self._on_kuma_speech_finished"
        in text
    )


def test_existing_avatar_error_bridge_still_consumes_legacy_error_signal():
    text = source(
        WINDOW
    )

    assert (
        "self.speech.speech_error.connect("
        in text
    )

    assert (
        "self._on_kuma_speech_error"
        in text
    )


def test_voice_1a_runtime_remains_provider_and_qt_free():
    text = source(
        RUNTIME
    )

    for forbidden in (
        "PySide",
        "QProcess",
        "Kokoro",
        "afplay",
        "/usr/bin/say",
        "speech_controller",
    ):
        assert (
            forbidden
            not in text
        ), forbidden


def test_adapter_documents_request_not_playback_boundary():
    text = source(
        CONTROLLER
    )

    for required in (
        "SPEAK REQUEST != PLAYBACK START",
        "QPROCESS STARTED == PLAYBACK TRUTH",
        "VOICE OUTPUT STATE != COGNITIVE STATE",
        "VOICE OUTPUT ERROR != TASK FAILURE",
        "VOICE OUTPUT AUTHORITY = NONE",
    ):
        assert (
            required
            in text
        )


def test_publish_helper_is_one_way_contract_projection():
    method = method_source(
        "_publish_output_state"
    )

    assert (
        "VoiceSnapshot("
        in method
    )

    assert (
        "self._voice_snapshot = snapshot"
        in method
    )

    assert (
        "self.voice_state_changed.emit("
        in method
    )


def test_publish_helper_returns_published_snapshot(
    controller,
):
    result = (
        controller
        ._publish_output_state(
            VoiceOutputMode.ERROR,
            reason="output failed",
        )
    )

    assert (
        result
        is controller.voice_snapshot
    )


def test_playing_transition_reason_is_bounded_contract_text(
    controller,
):
    result = (
        controller
        ._publish_output_state(
            VoiceOutputMode.PLAYING,
            reason="audio playback started",
        )
    )

    assert (
        result.reason
        == "audio playback started"
    )


def test_error_transition_is_not_task_failure_authority(
    controller,
):
    result = (
        controller
        ._publish_output_state(
            VoiceOutputMode.ERROR,
            reason="audio playback failed",
        )
    )

    assert (
        result.authority
        == "NONE"
    )

    assert (
        result.playback_active
        is False
    )


def test_synthesis_transition_is_not_playback_truth(
    controller,
):
    result = (
        controller
        ._publish_output_state(
            VoiceOutputMode.SYNTHESIZING,
            reason="accepted",
        )
    )

    assert (
        result.playback_active
        is False
    )


def test_idle_transition_is_not_playback_truth(
    controller,
):
    controller._publish_output_state(
        VoiceOutputMode.PLAYING,
        reason="playing",
    )

    result = (
        controller
        ._publish_output_state(
            VoiceOutputMode.IDLE,
            reason="complete",
        )
    )

    assert (
        result.playback_active
        is False
    )


def test_no_new_background_loop_added_for_voice_state():
    tree = parsed(
        CONTROLLER
    )

    publish_method = next(
        node
        for node in ast.walk(
            tree
        )
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name
            == "_publish_output_state"
        )
    )

    assert not any(
        isinstance(
            node,
            (
                ast.While,
                ast.AsyncFunctionDef,
            ),
        )
        for node in ast.walk(
            publish_method
        )
    )


def test_no_voice_state_timer_added():
    method = method_source(
        "_publish_output_state"
    )

    assert (
        "QTimer"
        not in method
    )


def test_output_state_signal_carries_snapshot_object_only():
    text = source(
        CONTROLLER
    )

    assert (
        "voice_state_changed = Signal(object)"
        in text
    )

    assert (
        "voice_state_changed = Signal(str)"
        not in text
    )


def test_speech_controller_still_has_no_agent_import():
    tree = parsed(
        CONTROLLER
    )

    modules = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ) and node.module:
            modules.add(
                node.module
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias in node.names
            )

    assert not any(
        name.startswith(
            "app.agent"
        )
        for name in modules
    )


def test_speech_controller_still_has_no_memory_import():
    tree = parsed(
        CONTROLLER
    )

    modules = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ) and node.module:
            modules.add(
                node.module
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias in node.names
            )

    assert not any(
        name.startswith(
            "app.memory"
        )
        for name in modules
    )


def test_speech_controller_still_has_no_tool_import():
    tree = parsed(
        CONTROLLER
    )

    modules = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ) and node.module:
            modules.add(
                node.module
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias in node.names
            )

    assert not any(
        name.startswith(
            "app.tools"
        )
        for name in modules
    )


def test_voice_state_reason_never_contains_spoken_text(
    controller,
):
    spoken = (
        "this is private spoken content"
    )

    result = (
        controller
        ._publish_output_state(
            VoiceOutputMode.SYNTHESIZING,
            reason="speech output accepted",
        )
    )

    assert (
        spoken
        not in result.reason
    )


def test_output_adapter_does_not_store_spoken_text_in_snapshot_source():
    method = method_source(
        "_publish_output_state"
    )

    assert (
        "self._active_text"
        not in method
    )

    assert (
        "text="
        not in method
    )


def test_stop_state_transition_is_conditional_on_non_idle_output():
    method = method_source(
        "stop"
    )

    assert (
        "was_output_active"
        in method
    )

    assert (
        "if was_output_active:"
        in method
    )


def test_speak_publishes_synthesizing_after_stop():
    method = method_source(
        "speak"
    )

    assert (
        method.index(
            "self.stop()"
        )
        < method.index(
            "VoiceOutputMode.SYNTHESIZING"
        )
    )


def test_playback_finished_generation_guard_precedes_state_change():
    method = method_source(
        "_on_playback_finished"
    )

    assert (
        method.index(
            "generation != self._generation"
        )
        < method.index(
            "VoiceOutputMode."
        )
    )


def test_playback_error_generation_guard_precedes_state_change():
    method = method_source(
        "_on_playback_error"
    )

    assert (
        method.index(
            "generation != self._generation"
        )
        < method.index(
            "VoiceOutputMode.ERROR"
        )
    )


def test_system_finished_generation_guard_precedes_state_change():
    method = method_source(
        "_on_system_finished"
    )

    assert (
        method.index(
            "generation != self._generation"
        )
        < method.index(
            "VoiceOutputMode."
        )
    )


def test_system_error_generation_guard_precedes_state_change():
    method = method_source(
        "_on_system_error"
    )

    assert (
        method.index(
            "generation != self._generation"
        )
        < method.index(
            "VoiceOutputMode.ERROR"
        )
    )
