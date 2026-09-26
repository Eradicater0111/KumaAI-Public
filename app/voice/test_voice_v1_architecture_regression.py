"""
KUMA-VOICE-1F / VOICE V1 final architecture regression.

This suite proves the final Voice V1 composition without opening hardware:

1A immutable zero-authority voice contract
1B truthful TTS output state
1C truthful microphone capture boundary
1D unified independent input/output truth
1E pure VoiceSnapshot -> AvatarSnapshot truth projection
1F outer live attachment + cleanup boundary

VOICE V1 remains zero-authority and contains no speech-to-text pipeline.
"""

from __future__ import annotations

import ast
from pathlib import Path

from PySide6.QtCore import (
    QObject,
    Signal,
)

from app.ui.avatar_runtime import (
    AvatarMode,
)
from app.voice.microphone_capture import (
    MicrophoneCaptureObservation,
)
from app.voice.voice_avatar_projection import (
    project_voice_snapshot_to_avatar,
)
from app.voice.voice_live_runtime import (
    KumaVoiceLiveRuntime,
)
from app.voice.voice_runtime import (
    VoiceInputMode,
    VoiceOutputMode,
    VoiceSnapshot,
)
from app.voice.voice_state_bridge import (
    KumaVoiceStateBridge,
)


ROOT = Path(
    "app/voice"
)

MAIN = Path(
    "app/main.py"
)

WINDOW = Path(
    "app/ui/window.py"
)

RUNTIME = (
    ROOT
    / "voice_runtime.py"
)

OUTPUT = (
    ROOT
    / "speech_controller.py"
)

MICROPHONE = (
    ROOT
    / "microphone_capture.py"
)

BRIDGE = (
    ROOT
    / "voice_state_bridge.py"
)

PROJECTION = (
    ROOT
    / "voice_avatar_projection.py"
)

LIVE = (
    ROOT
    / "voice_live_runtime.py"
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
        return (
            self._snapshot
        )

    def publish(
        self,
        snapshot,
    ):
        self._snapshot = (
            snapshot
        )

        self.voice_state_changed.emit(
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

        self.start_count = 0
        self.stop_count = 0
        self.close_count = 0

    @property
    def observation(
        self,
    ):
        return (
            self._observation
        )

    def start_capture(
        self,
    ):
        self.start_count += 1
        return True

    def stop_capture(
        self,
    ):
        self.stop_count += 1
        return True

    def probe_availability(
        self,
    ):
        return True

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


class FakeBody:
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


def test_voice_v1_file_inventory_contains_all_semantic_layers():
    expected = {
        "voice_runtime.py",
        "speech_controller.py",
        "microphone_capture.py",
        "voice_state_bridge.py",
        "voice_avatar_projection.py",
        "voice_live_runtime.py",
    }

    actual = {
        path.name
        for path in ROOT.glob(
            "*.py"
        )
    }

    assert expected.issubset(
        actual
    )


def test_voice_v1_contract_remains_authority_none():
    snapshot = VoiceSnapshot()

    assert (
        snapshot.authority
        == "NONE"
    )


def test_voice_v1_capture_truth_contract_remains_exact():
    snapshot = VoiceSnapshot(
        input_mode=(
            VoiceInputMode.CAPTURING
        ),
        microphone_active=True,
    )

    assert (
        snapshot.microphone_active
        is True
    )


def test_voice_v1_playback_truth_contract_remains_exact():
    snapshot = VoiceSnapshot(
        output_mode=(
            VoiceOutputMode.PLAYING
        ),
        playback_active=True,
    )

    assert (
        snapshot.playback_active
        is True
    )


def test_voice_v1_projection_capture_to_listening():
    avatar = (
        project_voice_snapshot_to_avatar(
            VoiceSnapshot(
                input_mode=(
                    VoiceInputMode.CAPTURING
                ),
                microphone_active=True,
            )
        )
    )

    assert (
        avatar.mode
        == AvatarMode.LISTENING
    )

    assert (
        avatar.authority
        == "NONE"
    )


def test_voice_v1_projection_playback_to_speaking():
    avatar = (
        project_voice_snapshot_to_avatar(
            VoiceSnapshot(
                output_mode=(
                    VoiceOutputMode.PLAYING
                ),
                playback_active=True,
            )
        )
    )

    assert (
        avatar.mode
        == AvatarMode.SPEAKING
    )

    assert (
        avatar.speech_active
        is True
    )


def test_voice_v1_simultaneous_truth_keeps_both_io_flags():
    snapshot = VoiceSnapshot(
        input_mode=(
            VoiceInputMode.CAPTURING
        ),
        output_mode=(
            VoiceOutputMode.PLAYING
        ),
        microphone_active=True,
        playback_active=True,
    )

    assert snapshot.microphone_active
    assert snapshot.playback_active

    avatar = (
        project_voice_snapshot_to_avatar(
            snapshot
        )
    )

    assert (
        avatar.mode
        == AvatarMode.SPEAKING
    )


def test_voice_v1_bridge_preserves_independent_truth():
    speech = FakeSpeech()
    microphone = FakeMicrophone()

    bridge = KumaVoiceStateBridge(
        speech,
        microphone,
    )

    microphone.publish(
        MicrophoneCaptureObservation(
            input_mode=(
                VoiceInputMode.CAPTURING
            ),
            microphone_active=True,
        )
    )

    speech.publish(
        VoiceSnapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            ),
            playback_active=True,
        )
    )

    snapshot = bridge.voice_snapshot

    assert snapshot.microphone_active
    assert snapshot.playback_active
    assert snapshot.authority == "NONE"


def test_voice_v1_live_runtime_does_not_start_microphone_on_construction():
    speech = FakeSpeech()
    microphone = FakeMicrophone()
    body = FakeBody()

    KumaVoiceLiveRuntime(
        speech,
        body,
        microphone_capture=microphone,
    )

    assert (
        microphone.start_count
        == 0
    )


def test_voice_v1_live_runtime_real_capture_event_reaches_listening_sink():
    speech = FakeSpeech()
    microphone = FakeMicrophone()
    body = FakeBody()

    runtime = KumaVoiceLiveRuntime(
        speech,
        body,
        microphone_capture=microphone,
    )

    microphone.publish(
        MicrophoneCaptureObservation(
            input_mode=(
                VoiceInputMode.CAPTURING
            ),
            microphone_active=True,
            reason="microphone audio bytes observed",
        )
    )

    assert (
        runtime.voice_snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        body.snapshots[-1].mode
        == AvatarMode.LISTENING
    )


def test_voice_v1_live_runtime_does_not_duplicate_speaking_sink():
    speech = FakeSpeech()
    microphone = FakeMicrophone()
    body = FakeBody()

    runtime = KumaVoiceLiveRuntime(
        speech,
        body,
        microphone_capture=microphone,
    )

    speech.publish(
        VoiceSnapshot(
            output_mode=(
                VoiceOutputMode.PLAYING
            ),
            playback_active=True,
        )
    )

    assert (
        runtime.voice_snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert (
        body.snapshots
        == []
    )


def test_voice_v1_live_runtime_cleanup_closes_microphone_boundary():
    speech = FakeSpeech()
    microphone = FakeMicrophone()
    body = FakeBody()

    runtime = KumaVoiceLiveRuntime(
        speech,
        body,
        microphone_capture=microphone,
    )

    runtime.close()

    assert (
        microphone.close_count
        == 1
    )


def test_voice_v1_bootstrap_is_external_to_frozen_window():
    main = MAIN.read_text()
    window = WINDOW.read_text()

    assert (
        "attach_kuma_voice_runtime"
        in main
    )

    assert (
        "attach_kuma_voice_runtime"
        not in window
    )

    assert (
        "voice_live_runtime"
        not in window
    )


def test_voice_v1_bootstrap_does_not_auto_enable_microphone():
    main = MAIN.read_text()

    for forbidden in (
        ".start_listening(",
        ".start_capture(",
        ".probe_microphone(",
        ".probe_availability(",
    ):
        assert forbidden not in main


def test_voice_v1_bootstrap_registers_explicit_shutdown_cleanup():
    main = MAIN.read_text()

    assert (
        ".aboutToQuit.connect("
        in main
    )

    assert (
        "voice_runtime.close"
        in main
    )


def test_voice_v1_frozen_window_retains_no_direct_listening_literal():
    window = WINDOW.read_text()

    assert (
        "AvatarMode.LISTENING"
        not in window
    )


def test_voice_v1_frozen_window_retains_truthful_speaking_path():
    window = WINDOW.read_text()

    assert (
        "AvatarMode.SPEAKING"
        in window
    )

    assert (
        "speech_active=True"
        in window
    )


def test_voice_v1_live_runtime_has_no_agent_import():
    tree = ast.parse(
        LIVE.read_text(),
        filename=str(LIVE),
    )

    modules = {
        node.module
        for node in ast.walk(
            tree
        )
        if (
            isinstance(
                node,
                ast.ImportFrom,
            )
            and node.module
        )
    }

    assert not any(
        module.startswith(
            "app.agent"
        )
        for module in modules
    )


def test_voice_v1_live_runtime_has_no_memory_import():
    text = LIVE.read_text()

    assert (
        "app.memory"
        not in text
    )


def test_voice_v1_live_runtime_has_no_tool_import():
    text = LIVE.read_text()

    assert (
        "app.tools"
        not in text
    )


def test_voice_v1_has_no_stt_provider_in_final_live_path():
    combined = "\n".join(
        path.read_text()
        for path in (
            LIVE,
            PROJECTION,
            BRIDGE,
            MICROPHONE,
        )
    ).lower()

    for forbidden in (
        "speech_recognition",
        "faster_whisper",
        "mlx_whisper",
        "import whisper",
    ):
        assert forbidden not in combined


def test_voice_v1_live_path_has_no_execution_calls():
    text = LIVE.read_text()

    for forbidden in (
        "request_confirmation(",
        ".execute(",
        "register_tool(",
        "require_explicit_permission(",
        "TaskState",
        "mark_finished(",
    ):
        assert forbidden not in text


def test_voice_v1_live_path_has_no_model_control():
    text = LIVE.read_text().lower()

    for forbidden in (
        "ollama",
        "google.genai",
        "openai",
        "model_warmup",
        "model.generate",
    ):
        assert forbidden not in text


def test_voice_v1_live_path_has_no_background_loop():
    text = LIVE.read_text()

    for forbidden in (
        "while True",
        "QThread",
        "QTimer",
        "threading",
        "asyncio",
    ):
        assert forbidden not in text


def test_voice_v1_main_has_exactly_one_live_attachment_call():
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


def test_voice_v1_main_keeps_single_qapplication_loop():
    text = MAIN.read_text()

    assert (
        text.count(
            ".exec()"
        )
        == 1
    )


def test_voice_v1_main_keeps_kumawindow_construction():
    text = MAIN.read_text()

    assert (
        "KumaWindow("
        in text
    )


def test_voice_v1_runtime_contract_documents_none_authority():
    text = RUNTIME.read_text()

    assert (
        'VOICE_AUTHORITY_NONE = "NONE"'
        in text
    )


def test_voice_v1_output_layer_documents_none_authority():
    text = OUTPUT.read_text()

    assert (
        "VOICE OUTPUT AUTHORITY = NONE"
        in text
    )


def test_voice_v1_microphone_layer_documents_none_authority():
    text = MICROPHONE.read_text()

    assert (
        "MICROPHONE AUTHORITY = NONE"
        in text
    )


def test_voice_v1_bridge_layer_documents_none_authority():
    text = BRIDGE.read_text()

    assert (
        "BRIDGE AUTHORITY = NONE"
        in text
    )


def test_voice_v1_projection_layer_documents_none_authority():
    text = PROJECTION.read_text()

    assert (
        "VOICE-AVATAR PROJECTION AUTHORITY = NONE"
        in text
    )


def test_voice_v1_live_layer_documents_none_authority():
    text = LIVE.read_text()

    assert (
        "VOICE V1 AUTHORITY = NONE"
        in text
    )


def test_voice_v1_final_stack_compiles():
    for path in (
        RUNTIME,
        OUTPUT,
        MICROPHONE,
        BRIDGE,
        PROJECTION,
        LIVE,
        MAIN,
    ):
        compile(
            path.read_text(),
            str(path),
            "exec",
        )
