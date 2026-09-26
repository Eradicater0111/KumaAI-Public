from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from PySide6.QtCore import (
    QObject,
    Signal,
)

from app.ui.avatar_runtime import (
    AvatarMode,
    AvatarSnapshot,
)
from app.voice.microphone_capture import (
    MicrophoneCaptureObservation,
)
from app.voice.voice_live_runtime import (
    KumaVoiceLiveRuntime,
    attach_kuma_voice_runtime,
)
from app.voice.voice_runtime import (
    VoiceInputMode,
    VoiceOutputMode,
    VoiceSnapshot,
)


MODULE = Path(
    "app/voice/voice_live_runtime.py"
)

MAIN = Path(
    "app/main.py"
)

WINDOW = Path(
    "app/ui/window.py"
)


class FakeSpeech(
    QObject
):
    voice_state_changed = Signal(
        object
    )
    speech_finished = Signal()
    speech_error = Signal(
        str
    )

    def __init__(
        self,
    ):
        super().__init__()

        self._snapshot = (
            VoiceSnapshot()
        )

    @property
    def voice_snapshot(
        self,
    ):
        return self._snapshot

    def publish(
        self,
        snapshot,
    ):
        self._snapshot = snapshot
        self.voice_state_changed.emit(
            snapshot
        )

    def finish(
        self,
    ):
        self.speech_finished.emit()

    def fail(
        self,
    ):
        self.speech_error.emit(
            "failure"
        )


class FakeBodyController:
    def __init__(
        self,
    ):
        self.snapshots = []

    def present_avatar_snapshot(
        self,
        snapshot,
    ):
        self.snapshots.append(
            snapshot
        )


class FakeMicrophone(
    QObject
):
    capture_state_changed = Signal(
        object
    )

    def __init__(
        self,
    ):
        super().__init__()

        self._observation = (
            MicrophoneCaptureObservation()
        )

        self.probe_count = 0
        self.start_count = 0
        self.stop_count = 0
        self.close_count = 0

        self.probe_result = True
        self.start_result = True
        self.stop_result = True

    @property
    def observation(
        self,
    ):
        return self._observation

    def probe_availability(
        self,
    ):
        self.probe_count += 1
        return self.probe_result

    def start_capture(
        self,
    ):
        self.start_count += 1
        return self.start_result

    def stop_capture(
        self,
    ):
        self.stop_count += 1
        return self.stop_result

    def close(
        self,
    ):
        self.close_count += 1

    def publish(
        self,
        observation,
    ):
        self._observation = (
            observation
        )

        self.capture_state_changed.emit(
            observation
        )


class FakeWindow(
    QObject
):
    def __init__(
        self,
    ):
        super().__init__()

        self.speech = FakeSpeech()
        self.body_controller = (
            FakeBodyController()
        )


def input_observation(
    mode,
    *,
    reason="",
):
    return (
        MicrophoneCaptureObservation(
            input_mode=mode,
            microphone_active=(
                mode
                == VoiceInputMode.CAPTURING
            ),
            reason=reason,
        )
    )


def output_snapshot(
    mode,
    *,
    reason="",
):
    return VoiceSnapshot(
        output_mode=mode,
        playback_active=(
            mode
            == VoiceOutputMode.PLAYING
        ),
        reason=reason,
    )


def make_runtime():
    speech = FakeSpeech()
    body = FakeBodyController()
    microphone = FakeMicrophone()

    runtime = KumaVoiceLiveRuntime(
        speech,
        body,
        microphone_capture=microphone,
    )

    return (
        runtime,
        speech,
        body,
        microphone,
    )


def module_tree():
    text = MODULE.read_text()

    return (
        text,
        ast.parse(
            text,
            filename=str(MODULE),
        ),
    )


def function_source(
    name,
):
    text, tree = module_tree()

    node = next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name == name
        )
    )

    return (
        ast.get_source_segment(
            text,
            node,
        )
        or ""
    )


def class_method_source(
    name,
):
    text, tree = module_tree()

    cls = next(
        node
        for node in tree.body
        if (
            isinstance(
                node,
                ast.ClassDef,
            )
            and node.name
            == "KumaVoiceLiveRuntime"
        )
    )

    node = next(
        node
        for node in cls.body
        if (
            isinstance(
                node,
                ast.FunctionDef,
            )
            and node.name == name
        )
    )

    return (
        ast.get_source_segment(
            text,
            node,
        )
        or ""
    )


def test_runtime_constructs_with_truth_sources():
    runtime, _, _, _ = make_runtime()

    assert isinstance(
        runtime,
        KumaVoiceLiveRuntime,
    )


def test_runtime_initial_voice_snapshot_is_unavailable_idle():
    runtime, _, _, _ = make_runtime()

    assert (
        runtime.voice_snapshot.input_mode
        == VoiceInputMode.UNAVAILABLE
    )

    assert (
        runtime.voice_snapshot.output_mode
        == VoiceOutputMode.IDLE
    )


def test_runtime_initial_authority_is_none():
    runtime, _, _, _ = make_runtime()

    assert (
        runtime.voice_snapshot.authority
        == "NONE"
    )


def test_runtime_exposes_microphone_capture_read_only_property():
    runtime, _, _, microphone = make_runtime()

    assert (
        runtime.microphone_capture
        is microphone
    )

    assert (
        KumaVoiceLiveRuntime
        .microphone_capture
        .fset
        is None
    )


def test_runtime_exposes_bridge_read_only_property():
    runtime, _, _, _ = make_runtime()

    assert (
        runtime.bridge
        is not None
    )

    assert (
        KumaVoiceLiveRuntime
        .bridge
        .fset
        is None
    )


def test_runtime_voice_snapshot_property_has_no_setter():
    assert (
        KumaVoiceLiveRuntime
        .voice_snapshot
        .fset
        is None
    )


def test_construction_does_not_probe_microphone():
    _, _, _, microphone = make_runtime()

    assert (
        microphone.probe_count
        == 0
    )


def test_construction_does_not_start_microphone():
    _, _, _, microphone = make_runtime()

    assert (
        microphone.start_count
        == 0
    )


def test_construction_does_not_stop_microphone():
    _, _, _, microphone = make_runtime()

    assert (
        microphone.stop_count
        == 0
    )


def test_probe_microphone_delegates_without_capture_start():
    runtime, _, _, microphone = make_runtime()

    assert (
        runtime.probe_microphone()
        is True
    )

    assert (
        microphone.probe_count
        == 1
    )

    assert (
        microphone.start_count
        == 0
    )


@pytest.mark.parametrize(
    "value",
    (
        True,
        False,
    ),
)
def test_probe_microphone_returns_strict_bool(
    value,
):
    runtime, _, _, microphone = make_runtime()

    microphone.probe_result = value

    assert (
        runtime.probe_microphone()
        is value
    )


def test_start_listening_delegates_exactly_once():
    runtime, _, _, microphone = make_runtime()

    assert (
        runtime.start_listening()
        is True
    )

    assert (
        microphone.start_count
        == 1
    )


def test_start_listening_does_not_fabricate_avatar_before_bytes():
    runtime, _, body, _ = make_runtime()

    runtime.start_listening()

    assert (
        body.snapshots
        == []
    )


@pytest.mark.parametrize(
    "value",
    (
        True,
        False,
    ),
)
def test_start_listening_returns_capture_result(
    value,
):
    runtime, _, _, microphone = make_runtime()

    microphone.start_result = value

    assert (
        runtime.start_listening()
        is value
    )


def test_real_capture_observation_presents_listening():
    runtime, _, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            VoiceInputMode.CAPTURING,
            reason="microphone audio bytes observed",
        )
    )

    assert (
        len(
            body.snapshots
        )
        == 1
    )

    assert (
        body.snapshots[0].mode
        == AvatarMode.LISTENING
    )


def test_listening_presentation_has_none_authority():
    runtime, _, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            VoiceInputMode.CAPTURING
        )
    )

    assert (
        body.snapshots[-1].authority
        == "NONE"
    )


def test_listening_presentation_is_not_speech_active():
    runtime, _, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            VoiceInputMode.CAPTURING
        )
    )

    assert (
        body.snapshots[-1].speech_active
        is False
    )


@pytest.mark.parametrize(
    "mode",
    (
        VoiceInputMode.UNAVAILABLE,
        VoiceInputMode.INACTIVE,
        VoiceInputMode.ERROR,
    ),
)
def test_non_capturing_input_does_not_present_listening(
    mode,
):
    runtime, _, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            mode
        )
    )

    assert (
        body.snapshots
        == []
    )


def test_playback_state_is_not_duplicated_into_body_sink():
    runtime, speech, body, _ = make_runtime()

    speech.publish(
        output_snapshot(
            VoiceOutputMode.PLAYING,
            reason="audio playback started",
        )
    )

    assert (
        body.snapshots
        == []
    )


def test_synthesizing_state_does_not_present_avatar():
    runtime, speech, body, _ = make_runtime()

    speech.publish(
        output_snapshot(
            VoiceOutputMode.SYNTHESIZING
        )
    )

    assert (
        body.snapshots
        == []
    )


def test_output_error_state_does_not_present_avatar():
    runtime, speech, body, _ = make_runtime()

    speech.publish(
        output_snapshot(
            VoiceOutputMode.ERROR
        )
    )

    assert (
        body.snapshots
        == []
    )


def test_active_capture_plus_playback_does_not_duplicate_speaking():
    runtime, speech, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            VoiceInputMode.CAPTURING
        )
    )

    body.snapshots.clear()

    speech.publish(
        VoiceSnapshot(
            input_mode=(
                VoiceInputMode.UNAVAILABLE
            ),
            output_mode=(
                VoiceOutputMode.PLAYING
            ),
            microphone_active=False,
            playback_active=True,
            reason="audio playback started",
        )
    )

    assert (
        runtime.voice_snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        runtime.voice_snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert (
        body.snapshots
        == []
    )


def test_playback_finish_reasserts_listening_when_capture_remains_active():
    runtime, speech, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            VoiceInputMode.CAPTURING
        )
    )

    body.snapshots.clear()

    speech.publish(
        output_snapshot(
            VoiceOutputMode.PLAYING
        )
    )

    speech.publish(
        output_snapshot(
            VoiceOutputMode.IDLE
        )
    )

    before_terminal_signal = len(
        body.snapshots
    )

    speech.finish()

    assert (
        len(
            body.snapshots
        )
        >= before_terminal_signal
    )

    assert (
        body.snapshots[-1].mode
        == AvatarMode.LISTENING
    )


def test_playback_error_signal_reasserts_listening_when_capture_active():
    runtime, speech, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            VoiceInputMode.CAPTURING
        )
    )

    body.snapshots.clear()

    speech.publish(
        output_snapshot(
            VoiceOutputMode.ERROR
        )
    )

    speech.fail()

    assert (
        body.snapshots[-1].mode
        == AvatarMode.LISTENING
    )


def test_terminal_speech_signal_does_not_present_when_microphone_inactive():
    runtime, speech, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            VoiceInputMode.INACTIVE
        )
    )

    speech.publish(
        output_snapshot(
            VoiceOutputMode.IDLE
        )
    )

    body.snapshots.clear()

    speech.finish()

    assert (
        body.snapshots
        == []
    )


def test_stop_listening_delegates_to_capture():
    runtime, _, _, microphone = make_runtime()

    assert (
        runtime.stop_listening()
        is True
    )

    assert (
        microphone.stop_count
        == 1
    )


def test_stop_listening_does_not_fabricate_idle_avatar():
    runtime, _, body, microphone = make_runtime()

    microphone.publish(
        input_observation(
            VoiceInputMode.CAPTURING
        )
    )

    body.snapshots.clear()

    runtime.stop_listening()

    assert (
        body.snapshots
        == []
    )


def test_close_delegates_to_microphone_close():
    runtime, _, _, microphone = make_runtime()

    runtime.close()

    assert (
        microphone.close_count
        == 1
    )


def test_runtime_requires_speech_voice_snapshot():
    class BadSpeech(
        QObject
    ):
        speech_finished = Signal()
        speech_error = Signal(
            str
        )

    with pytest.raises(
        TypeError,
        match="voice_snapshot",
    ):
        KumaVoiceLiveRuntime(
            BadSpeech(),
            FakeBodyController(),
            microphone_capture=(
                FakeMicrophone()
            ),
        )


def test_runtime_requires_body_presentation_sink():
    with pytest.raises(
        TypeError,
        match="present_avatar_snapshot",
    ):
        KumaVoiceLiveRuntime(
            FakeSpeech(),
            object(),
            microphone_capture=(
                FakeMicrophone()
            ),
        )


def test_attach_requires_window_speech():
    window = QObject()
    window.body_controller = (
        FakeBodyController()
    )

    with pytest.raises(
        TypeError,
        match="speech",
    ):
        attach_kuma_voice_runtime(
            window
        )


def test_attach_requires_window_body_controller():
    window = QObject()
    window.speech = FakeSpeech()

    with pytest.raises(
        TypeError,
        match="body_controller",
    ):
        attach_kuma_voice_runtime(
            window
        )


def test_attach_returns_runtime():
    window = FakeWindow()

    runtime = (
        attach_kuma_voice_runtime(
            window
        )
    )

    assert isinstance(
        runtime,
        KumaVoiceLiveRuntime,
    )


def test_attach_stores_runtime_on_window_for_lifetime():
    window = FakeWindow()

    runtime = (
        attach_kuma_voice_runtime(
            window
        )
    )

    assert (
        window._kuma_voice_runtime
        is runtime
    )


def test_attach_is_idempotent():
    window = FakeWindow()

    first = (
        attach_kuma_voice_runtime(
            window
        )
    )

    second = (
        attach_kuma_voice_runtime(
            window
        )
    )

    assert (
        first
        is second
    )


def test_attach_rejects_incompatible_existing_runtime():
    window = FakeWindow()

    window._kuma_voice_runtime = (
        object()
    )

    with pytest.raises(
        RuntimeError,
        match="incompatible",
    ):
        attach_kuma_voice_runtime(
            window
        )


def test_attach_does_not_start_microphone():
    source = function_source(
        "attach_kuma_voice_runtime"
    )

    assert (
        ".start_listening("
        not in source
    )

    assert (
        ".start_capture("
        not in source
    )

    assert (
        ".probe_microphone("
        not in source
    )

    assert (
        ".probe_availability("
        not in source
    )


def test_runtime_constructor_does_not_start_microphone():
    source = class_method_source(
        "__init__"
    )

    for forbidden in (
        ".start_capture(",
        ".start_listening(",
        ".probe_availability(",
        ".probe_microphone(",
    ):
        assert forbidden not in source


def test_start_listening_does_not_present_avatar_directly():
    source = class_method_source(
        "start_listening"
    )

    assert (
        "present_avatar_snapshot"
        not in source
    )

    assert (
        "AvatarMode.LISTENING"
        not in source
    )


def test_listening_sink_is_projection_driven():
    source = class_method_source(
        "_present_listening_if_owned"
    )

    assert (
        "project_voice_snapshot_to_avatar("
        in source
    )

    assert (
        "AvatarMode.LISTENING"
        in source
    )

    assert (
        "present_avatar_snapshot("
        in source
    )


def test_live_bridge_handler_does_not_construct_avatar_snapshot():
    source = class_method_source(
        "_on_voice_state_changed"
    )

    assert (
        "AvatarSnapshot("
        not in source
    )


def test_runtime_never_constructs_avatar_snapshot_directly():
    text = MODULE.read_text()

    assert (
        "AvatarSnapshot("
        not in text
    )


def test_runtime_does_not_import_avatar_snapshot():
    text, tree = module_tree()

    imported = {
        alias.name
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            ast.ImportFrom,
        )
        for alias in node.names
    }

    assert (
        "AvatarSnapshot"
        not in imported
    )


def test_runtime_does_not_write_direct_body_state():
    text = MODULE.read_text()

    for forbidden in (
        ".set_state(",
        "KumaBodyState",
        "bodyState",
        "setProperty(",
    ):
        assert forbidden not in text


def test_runtime_uses_existing_body_controller_sink_only():
    source = class_method_source(
        "_present_listening_if_owned"
    )

    assert (
        "self._body_controller.present_avatar_snapshot("
        in source
    )


def test_runtime_does_not_duplicate_speaking_sink():
    source = class_method_source(
        "_present_listening_if_owned"
    )

    assert (
        "AvatarMode.SPEAKING"
        not in source
    )


def test_runtime_documents_existing_speaking_owner():
    text = MODULE.read_text()

    assert (
        "SPEAKING PRESENTATION REMAINS OWNED BY THE FROZEN WINDOW PLAYBACK PATH"
        in text
    )


def test_runtime_documents_no_auto_microphone():
    text = MODULE.read_text()

    assert (
        "RUNTIME ATTACHMENT != MICROPHONE START"
        in text
    )

    assert (
        "does not auto-start microphone capture"
        in text
    )


def test_runtime_documents_no_transcription():
    text = MODULE.read_text()

    assert (
        "RUNTIME ATTACHMENT != TRANSCRIPTION"
        in text
    )


def test_runtime_documents_zero_authority():
    text = MODULE.read_text()

    for required in (
        "LIVE VOICE RUNTIME != COGNITION",
        "LIVE VOICE RUNTIME != COMMAND AUTHORITY",
        "MICROPHONE CAPTURE != COMMAND",
        "PLAYBACK != MODEL CONTROL",
        "AVATAR PRESENTATION != PERMISSION",
        "VOICE V1 AUTHORITY = NONE",
    ):
        assert required in text


def test_runtime_has_no_stt_provider_imports():
    text = MODULE.read_text().lower()

    for forbidden in (
        "speech_recognition",
        "whisper",
        "faster_whisper",
        "mlx_whisper",
    ):
        assert forbidden not in text


def test_runtime_has_no_agent_memory_tool_imports():
    _, tree = module_tree()

    modules = set()

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

        elif isinstance(
            node,
            ast.Import,
        ):
            modules.update(
                alias.name
                for alias in node.names
            )

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


def test_runtime_has_no_network_imports():
    _, tree = module_tree()

    roots = set()

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
            roots.add(
                node.module.split(
                    ".",
                    1,
                )[0]
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            roots.update(
                alias.name.split(
                    ".",
                    1,
                )[0]
                for alias in node.names
            )

    assert roots.isdisjoint(
        {
            "requests",
            "httpx",
            "urllib",
            "socket",
            "aiohttp",
            "websockets",
        }
    )


def test_runtime_has_no_model_import():
    text = MODULE.read_text().lower()

    for forbidden in (
        "google.genai",
        "ollama",
        "openai",
        "model_warmup",
    ):
        assert forbidden not in text


def test_runtime_has_no_background_loop():
    text = MODULE.read_text()

    for forbidden in (
        "while True",
        "QThread",
        "threading",
        "asyncio",
        "QTimer",
    ):
        assert forbidden not in text


def test_runtime_has_no_file_persistence():
    text = MODULE.read_text()

    for forbidden in (
        "Path(",
        "open(",
        "sqlite",
        "write_text(",
        "write_bytes(",
        "tempfile",
    ):
        assert forbidden not in text


def test_runtime_does_not_import_window():
    text = MODULE.read_text()

    assert (
        "app.ui.window"
        not in text
    )


def test_main_imports_live_attachment():
    text = MAIN.read_text()

    assert (
        "from app.voice.voice_live_runtime import"
        in text
    )

    assert (
        "attach_kuma_voice_runtime"
        in text
    )


def test_main_attaches_runtime_to_constructed_window():
    text = MAIN.read_text()

    tree = ast.parse(
        text,
        filename=str(MAIN),
    )

    calls = [
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
            == "attach_kuma_voice_runtime"
        )
    ]

    assert (
        len(calls)
        == 1
    )


def test_main_does_not_auto_start_listening():
    text = MAIN.read_text()

    assert (
        ".start_listening("
        not in text
    )

    assert (
        ".start_capture("
        not in text
    )

    assert (
        ".probe_microphone("
        not in text
    )


def test_main_connects_application_shutdown_to_voice_close():
    text = MAIN.read_text()

    assert (
        ".aboutToQuit.connect("
        in text
    )

    assert (
        ".close"
        in text
    )


def test_main_attaches_before_event_loop():
    text = MAIN.read_text()

    attach = text.index(
        "attach_kuma_voice_runtime"
    )

    # use the call, not the import
    attach = text.index(
        "attach_kuma_voice_runtime(",
        attach,
    )

    event_loop = text.index(
        ".exec()"
    )

    assert (
        attach
        < event_loop
    )


def test_main_keeps_kumawindow_construction():
    text = MAIN.read_text()

    assert (
        "KumaWindow("
        in text
    )


def test_main_keeps_qapplication_event_loop():
    text = MAIN.read_text()

    assert (
        "QApplication("
        in text
    )

    assert (
        ".exec()"
        in text
    )


def test_window_remains_without_voice_1f_import():
    text = WINDOW.read_text()

    assert (
        "voice_live_runtime"
        not in text
    )

    assert (
        "KumaVoiceLiveRuntime"
        not in text
    )

    assert (
        "attach_kuma_voice_runtime"
        not in text
    )


def test_window_still_has_no_direct_avatar_listening_source():
    text = WINDOW.read_text()

    assert (
        "AvatarMode.LISTENING"
        not in text
    )


def test_window_still_owns_existing_speaking_path():
    text = WINDOW.read_text()

    assert (
        "AvatarMode.SPEAKING"
        in text
    )

    assert (
        "speech_active=True"
        in text
    )


def test_runtime_start_listening_has_no_authority_parameter():
    signature = inspect.signature(
        KumaVoiceLiveRuntime
        .start_listening
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
        "command"
        not in signature.parameters
    )


def test_runtime_stop_listening_has_no_authority_parameter():
    signature = inspect.signature(
        KumaVoiceLiveRuntime
        .stop_listening
    )

    assert (
        "authority"
        not in signature.parameters
    )

    assert (
        "permission"
        not in signature.parameters
    )


def test_attach_has_no_authority_parameter():
    signature = inspect.signature(
        attach_kuma_voice_runtime
    )

    assert tuple(
        signature.parameters
    ) == (
        "window",
    )


def test_runtime_close_returns_none():
    runtime, _, _, microphone = make_runtime()

    assert (
        runtime.close()
        is None
    )

    assert (
        microphone.close_count
        == 1
    )


def test_live_runtime_module_compiles():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
