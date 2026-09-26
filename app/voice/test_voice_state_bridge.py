from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path

import pytest

from PySide6.QtCore import (
    QObject,
    Signal,
)

from app.voice.microphone_capture import (
    MicrophoneCaptureObservation,
)
from app.voice.voice_runtime import (
    VoiceInputMode,
    VoiceOutputMode,
    VoiceSnapshot,
    VoiceTranscript,
    idle_voice_snapshot,
)
from app.voice.voice_state_bridge import (
    KumaVoiceStateBridge,
)


MODULE = Path(
    "app/voice/voice_state_bridge.py"
)

WINDOW = Path(
    "app/ui/window.py"
)


class FakeSpeechSource(
    QObject
):
    voice_state_changed = Signal(
        object
    )

    def __init__(
        self,
        snapshot=None,
    ):
        super().__init__()

        self._snapshot = (
            snapshot
            if snapshot is not None
            else idle_voice_snapshot()
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


class FakeMicrophoneSource(
    QObject
):
    capture_state_changed = Signal(
        object
    )

    def __init__(
        self,
        observation=None,
    ):
        super().__init__()

        self._observation = (
            observation
            if observation is not None
            else MicrophoneCaptureObservation()
        )

    @property
    def observation(
        self,
    ):
        return self._observation

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


def output_snapshot(
    *,
    output=VoiceOutputMode.IDLE,
    input_mode=VoiceInputMode.UNAVAILABLE,
    microphone_active=False,
    transcript=None,
    reason="",
):
    return VoiceSnapshot(
        input_mode=input_mode,
        output_mode=output,
        microphone_active=(
            microphone_active
        ),
        playback_active=(
            output
            == VoiceOutputMode.PLAYING
        ),
        transcript=transcript,
        reason=reason,
    )


def input_observation(
    *,
    mode=VoiceInputMode.UNAVAILABLE,
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


def make_bridge(
    *,
    output=None,
    input_state=None,
):
    speech = FakeSpeechSource(
        output
    )

    microphone = (
        FakeMicrophoneSource(
            input_state
        )
    )

    bridge = KumaVoiceStateBridge(
        speech,
        microphone,
    )

    return (
        bridge,
        speech,
        microphone,
    )


def events_from(
    bridge,
):
    events = []

    bridge.voice_state_changed.connect(
        events.append
    )

    return events


def class_source():
    text = MODULE.read_text()

    tree = ast.parse(
        text,
        filename=str(MODULE),
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
            == "KumaVoiceStateBridge"
        )
    )

    return (
        text,
        cls,
    )


def method_source(
    name,
):
    text, cls = class_source()

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


def test_bridge_initial_snapshot_is_voice_snapshot():
    bridge, _, _ = make_bridge()

    assert isinstance(
        bridge.voice_snapshot,
        VoiceSnapshot,
    )


def test_bridge_initial_authority_is_none():
    bridge, _, _ = make_bridge()

    assert (
        bridge.voice_snapshot.authority
        == "NONE"
    )


def test_bridge_initial_input_truth_comes_from_microphone():
    bridge, _, _ = make_bridge(
        input_state=input_observation(
            mode=VoiceInputMode.INACTIVE
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        bridge.voice_snapshot.microphone_active
        is False
    )


def test_bridge_initial_capturing_truth_comes_from_microphone():
    bridge, _, _ = make_bridge(
        input_state=input_observation(
            mode=VoiceInputMode.CAPTURING
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        bridge.voice_snapshot.microphone_active
        is True
    )


@pytest.mark.parametrize(
    "mode",
    (
        VoiceOutputMode.IDLE,
        VoiceOutputMode.SYNTHESIZING,
        VoiceOutputMode.ERROR,
    ),
)
def test_bridge_initial_noncapturing_output_truth(
    mode,
):
    bridge, _, _ = make_bridge(
        output=output_snapshot(
            output=mode
        )
    )

    assert (
        bridge.voice_snapshot.output_mode
        == mode
    )

    assert (
        bridge.voice_snapshot.playback_active
        is False
    )


def test_bridge_initial_playing_truth_comes_from_speech():
    bridge, _, _ = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.PLAYING
        )
    )

    assert (
        bridge.voice_snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert (
        bridge.voice_snapshot.playback_active
        is True
    )


def test_bridge_allows_simultaneous_capture_and_playback_truth():
    bridge, _, _ = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.PLAYING
        ),
        input_state=input_observation(
            mode=VoiceInputMode.CAPTURING
        ),
    )

    snapshot = bridge.voice_snapshot

    assert (
        snapshot.microphone_active
        is True
    )

    assert (
        snapshot.playback_active
        is True
    )


def test_bridge_initial_reason_is_neutral():
    bridge, _, _ = make_bridge(
        output=output_snapshot(
            reason="old output reason"
        ),
        input_state=input_observation(
            reason="old input reason"
        ),
    )

    assert (
        bridge.voice_snapshot.reason
        == ""
    )


def test_bridge_initial_transcript_is_preserved_from_existing_snapshot():
    transcript = VoiceTranscript(
        "existing transcript"
    )

    bridge, _, _ = make_bridge(
        output=output_snapshot(
            transcript=transcript
        )
    )

    assert (
        bridge.voice_snapshot.transcript
        is transcript
    )


def test_voice_snapshot_property_has_no_setter():
    descriptor = (
        KumaVoiceStateBridge.voice_snapshot
    )

    assert isinstance(
        descriptor,
        property,
    )

    assert (
        descriptor.fset
        is None
    )


def test_bridge_snapshot_is_immutable():
    bridge, _, _ = make_bridge()

    with pytest.raises(
        FrozenInstanceError
    ):
        bridge.voice_snapshot.reason = (
            "changed"
        )


def test_input_update_changes_only_input_side():
    bridge, speech, microphone = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="playing",
        )
    )

    del speech

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING,
            reason="microphone bytes observed",
        )
    )

    snapshot = bridge.voice_snapshot

    assert (
        snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        snapshot.microphone_active
        is True
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert (
        snapshot.playback_active
        is True
    )


@pytest.mark.parametrize(
    "output_mode",
    (
        VoiceOutputMode.IDLE,
        VoiceOutputMode.SYNTHESIZING,
        VoiceOutputMode.PLAYING,
        VoiceOutputMode.ERROR,
    ),
)
def test_input_update_preserves_each_output_mode(
    output_mode,
):
    bridge, _, microphone = make_bridge(
        output=output_snapshot(
            output=output_mode
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING,
            reason="input change",
        )
    )

    assert (
        bridge.voice_snapshot.output_mode
        == output_mode
    )

    assert (
        bridge.voice_snapshot.playback_active
        is (
            output_mode
            == VoiceOutputMode.PLAYING
        )
    )


@pytest.mark.parametrize(
    "input_mode",
    (
        VoiceInputMode.UNAVAILABLE,
        VoiceInputMode.INACTIVE,
        VoiceInputMode.CAPTURING,
        VoiceInputMode.ERROR,
    ),
)
def test_output_update_preserves_each_input_mode(
    input_mode,
):
    bridge, speech, _ = make_bridge(
        input_state=input_observation(
            mode=input_mode
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="output change",
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == input_mode
    )

    assert (
        bridge.voice_snapshot.microphone_active
        is (
            input_mode
            == VoiceInputMode.CAPTURING
        )
    )


def test_output_update_changes_only_output_side():
    bridge, speech, _ = make_bridge(
        input_state=input_observation(
            mode=VoiceInputMode.CAPTURING,
            reason="capturing",
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="playback started",
        )
    )

    snapshot = bridge.voice_snapshot

    assert (
        snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        snapshot.microphone_active
        is True
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert (
        snapshot.playback_active
        is True
    )


def test_conflicting_input_fields_on_output_event_are_ignored():
    bridge, speech, _ = make_bridge(
        input_state=input_observation(
            mode=VoiceInputMode.INACTIVE
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            input_mode=(
                VoiceInputMode.CAPTURING
            ),
            microphone_active=True,
            reason="output event",
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        bridge.voice_snapshot.microphone_active
        is False
    )

    assert (
        bridge.voice_snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )


def test_input_event_cannot_change_output_truth():
    bridge, _, microphone = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.SYNTHESIZING
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.ERROR,
            reason="input error",
        )
    )

    assert (
        bridge.voice_snapshot.output_mode
        == VoiceOutputMode.SYNTHESIZING
    )

    assert (
        bridge.voice_snapshot.playback_active
        is False
    )


def test_output_event_cannot_change_microphone_truth():
    bridge, speech, _ = make_bridge(
        input_state=input_observation(
            mode=VoiceInputMode.CAPTURING
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.ERROR,
            reason="output error",
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        bridge.voice_snapshot.microphone_active
        is True
    )


def test_input_event_reason_becomes_unified_reason():
    bridge, _, microphone = make_bridge()

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.INACTIVE,
            reason="microphone available",
        )
    )

    assert (
        bridge.voice_snapshot.reason
        == "microphone available"
    )


def test_output_event_reason_becomes_unified_reason():
    bridge, speech, _ = make_bridge()

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.SYNTHESIZING,
            reason="speech accepted",
        )
    )

    assert (
        bridge.voice_snapshot.reason
        == "speech accepted"
    )


def test_input_then_output_preserves_latest_truth_from_each_source():
    bridge, speech, microphone = make_bridge()

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING,
            reason="capture",
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="playback",
        )
    )

    snapshot = bridge.voice_snapshot

    assert (
        snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert snapshot.microphone_active
    assert snapshot.playback_active
    assert snapshot.reason == "playback"


def test_output_then_input_preserves_latest_truth_from_each_source():
    bridge, speech, microphone = make_bridge()

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="playback",
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING,
            reason="capture",
        )
    )

    snapshot = bridge.voice_snapshot

    assert (
        snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert snapshot.microphone_active
    assert snapshot.playback_active
    assert snapshot.reason == "capture"


def test_input_stop_preserves_playback():
    bridge, _, microphone = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.PLAYING
        ),
        input_state=input_observation(
            mode=VoiceInputMode.CAPTURING
        ),
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.INACTIVE,
            reason="microphone capture stopped",
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        bridge.voice_snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )

    assert (
        bridge.voice_snapshot.playback_active
        is True
    )


def test_playback_finish_preserves_capture():
    bridge, speech, _ = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.PLAYING
        ),
        input_state=input_observation(
            mode=VoiceInputMode.CAPTURING
        ),
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.IDLE,
            reason="speech output finished",
        )
    )

    assert (
        bridge.voice_snapshot.output_mode
        == VoiceOutputMode.IDLE
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        bridge.voice_snapshot.microphone_active
        is True
    )


def test_input_error_preserves_output_playing_truth():
    bridge, _, microphone = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.PLAYING
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.ERROR,
            reason="microphone failed",
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.ERROR
    )

    assert (
        bridge.voice_snapshot.output_mode
        == VoiceOutputMode.PLAYING
    )


def test_output_error_preserves_input_capture_truth():
    bridge, speech, _ = make_bridge(
        input_state=input_observation(
            mode=VoiceInputMode.CAPTURING
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.ERROR,
            reason="speech failed",
        )
    )

    assert (
        bridge.voice_snapshot.output_mode
        == VoiceOutputMode.ERROR
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.CAPTURING
    )


def test_identical_input_event_does_not_emit_duplicate_snapshot():
    observation = input_observation(
        mode=VoiceInputMode.INACTIVE,
        reason="same",
    )

    bridge, _, microphone = make_bridge(
        input_state=observation
    )

    events = events_from(
        bridge
    )

    microphone.publish(
        observation
    )

    assert (
        len(events)
        == 1
    )

    # The first event changes the bridge reason from neutral to "same".
    microphone.publish(
        observation
    )

    assert (
        len(events)
        == 1
    )


def test_identical_output_event_does_not_emit_duplicate_snapshot():
    snapshot = output_snapshot(
        output=VoiceOutputMode.IDLE,
        reason="same",
    )

    bridge, speech, _ = make_bridge(
        output=snapshot
    )

    events = events_from(
        bridge
    )

    speech.publish(
        snapshot
    )

    assert (
        len(events)
        == 1
    )

    speech.publish(
        snapshot
    )

    assert (
        len(events)
        == 1
    )


def test_bridge_signal_emits_voice_snapshot():
    bridge, speech, _ = make_bridge()

    events = events_from(
        bridge
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="started",
        )
    )

    assert (
        len(events)
        == 1
    )

    assert isinstance(
        events[0],
        VoiceSnapshot,
    )


def test_bridge_signal_emitted_after_internal_snapshot_update():
    bridge, speech, _ = make_bridge()

    observed = []

    def callback(
        snapshot,
    ):
        observed.append(
            (
                snapshot,
                bridge.voice_snapshot,
            )
        )

    bridge.voice_state_changed.connect(
        callback
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="started",
        )
    )

    assert (
        observed[0][0]
        is observed[0][1]
    )


def test_input_event_does_not_mutate_source_observation():
    observation = input_observation(
        mode=VoiceInputMode.CAPTURING,
        reason="capture"
    )

    bridge, _, microphone = make_bridge()

    microphone.publish(
        observation
    )

    assert (
        microphone.observation
        is observation
    )

    assert (
        observation.reason
        == "capture"
    )

    assert (
        bridge.voice_snapshot
        is not observation
    )


def test_output_event_does_not_mutate_source_snapshot():
    snapshot = output_snapshot(
        output=VoiceOutputMode.PLAYING,
        reason="playback",
    )

    bridge, speech, _ = make_bridge()

    speech.publish(
        snapshot
    )

    assert (
        speech.voice_snapshot
        is snapshot
    )

    assert (
        snapshot.reason
        == "playback"
    )

    assert (
        bridge.voice_snapshot
        is not snapshot
    )


def test_transcript_is_preserved_across_input_update():
    transcript = VoiceTranscript(
        "existing transcript"
    )

    bridge, _, microphone = make_bridge(
        output=output_snapshot(
            transcript=transcript
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING,
            reason="capture",
        )
    )

    assert (
        bridge.voice_snapshot.transcript
        is transcript
    )


def test_transcript_is_preserved_across_output_update():
    transcript = VoiceTranscript(
        "existing transcript"
    )

    bridge, speech, _ = make_bridge(
        output=output_snapshot(
            transcript=transcript
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            transcript=VoiceTranscript(
                "foreign output transcript"
            ),
            reason="playback",
        )
    )

    assert (
        bridge.voice_snapshot.transcript
        is transcript
    )


def test_bridge_does_not_create_transcript_when_none():
    bridge, speech, microphone = make_bridge()

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING
        )
    )

    assert (
        bridge.voice_snapshot.transcript
        is None
    )


def test_bridge_rejects_invalid_initial_output_snapshot():
    class BadSpeech(
        QObject
    ):
        voice_state_changed = Signal(
            object
        )

        voice_snapshot = object()

    with pytest.raises(
        TypeError,
        match="VoiceSnapshot",
    ):
        KumaVoiceStateBridge(
            BadSpeech(),
            FakeMicrophoneSource(),
        )


def test_bridge_rejects_invalid_initial_input_observation():
    class BadMicrophone(
        QObject
    ):
        capture_state_changed = Signal(
            object
        )

        observation = object()

    with pytest.raises(
        TypeError,
        match="MicrophoneCaptureObservation",
    ):
        KumaVoiceStateBridge(
            FakeSpeechSource(),
            BadMicrophone(),
        )


def test_bridge_rejects_invalid_live_output_event():
    bridge, _, _ = make_bridge()

    with pytest.raises(
        TypeError,
        match="VoiceSnapshot",
    ):
        bridge._on_output_state_changed(
            object()
        )

    assert isinstance(
        bridge.voice_snapshot,
        VoiceSnapshot,
    )


def test_bridge_rejects_invalid_live_input_event():
    bridge, _, _ = make_bridge()

    with pytest.raises(
        TypeError,
        match="MicrophoneCaptureObservation",
    ):
        bridge._on_input_state_changed(
            object()
        )

    assert isinstance(
        bridge.voice_snapshot,
        VoiceSnapshot,
    )


def test_require_output_snapshot_is_strict():
    method = (
        KumaVoiceStateBridge
        ._require_output_snapshot
    )

    with pytest.raises(
        TypeError
    ):
        method(
            object()
        )


def test_require_input_observation_is_strict():
    method = (
        KumaVoiceStateBridge
        ._require_input_observation
    )

    with pytest.raises(
        TypeError
    ):
        method(
            object()
        )


def test_compose_does_not_accept_authority_parameter():
    signature = inspect.signature(
        KumaVoiceStateBridge._compose
    )

    assert (
        "authority"
        not in signature.parameters
    )


def test_compose_does_not_accept_microphone_active_parameter():
    signature = inspect.signature(
        KumaVoiceStateBridge._compose
    )

    assert (
        "microphone_active"
        not in signature.parameters
    )


def test_compose_does_not_accept_playback_active_parameter():
    signature = inspect.signature(
        KumaVoiceStateBridge._compose
    )

    assert (
        "playback_active"
        not in signature.parameters
    )


def test_bridge_constructor_does_not_start_microphone_or_speech():
    text = method_source(
        "__init__"
    )

    for forbidden in (
        ".start_capture(",
        ".probe_availability(",
        ".speak(",
        ".start(",
    ):
        assert forbidden not in text


def test_bridge_has_no_stop_side_effect_calls():
    text = MODULE.read_text()

    for forbidden in (
        ".stop_capture(",
        ".stop()",
        ".kill()",
    ):
        assert forbidden not in text


def test_bridge_never_writes_source_private_state():
    text = MODULE.read_text()

    tree = ast.parse(
        text,
        filename=str(MODULE),
    )

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            (
                ast.Assign,
                ast.AnnAssign,
                ast.AugAssign,
            ),
        ):
            segment = (
                ast.get_source_segment(
                    text,
                    node,
                )
                or ""
            )

            assert (
                "self._speech_controller."
                not in segment
            )

            assert (
                "self._microphone_capture."
                not in segment
            )


def test_input_handler_uses_cached_output_snapshot():
    method = method_source(
        "_on_input_state_changed"
    )

    assert (
        "self._output_snapshot"
        in method
    )


def test_output_handler_uses_cached_input_observation():
    method = method_source(
        "_on_output_state_changed"
    )

    assert (
        "self._input_observation"
        in method
    )


def test_input_handler_does_not_read_output_source_live():
    method = method_source(
        "_on_input_state_changed"
    )

    assert (
        "self._speech_controller.voice_snapshot"
        not in method
    )


def test_output_handler_does_not_read_input_source_live():
    method = method_source(
        "_on_output_state_changed"
    )

    assert (
        "self._microphone_capture.observation"
        not in method
    )


def test_compose_maps_input_fields_only_from_microphone_observation():
    method = method_source(
        "_compose"
    )

    assert (
        "input_observation.input_mode"
        in method
    )

    assert (
        "input_observation.microphone_active"
        in method
    )


def test_compose_maps_output_fields_only_from_output_snapshot():
    method = method_source(
        "_compose"
    )

    assert (
        "output_snapshot.output_mode"
        in method
    )

    assert (
        "output_snapshot.playback_active"
        in method
    )


def test_compose_preserves_current_transcript():
    method = method_source(
        "_compose"
    )

    assert (
        "self._voice_snapshot.transcript"
        in method
    )


def test_bridge_declares_one_unified_state_signal():
    text = MODULE.read_text()

    assert (
        "voice_state_changed = Signal("
        in text
    )

    assert (
        "capture_state_changed = Signal("
        not in text
    )

    assert (
        "speech_started = Signal("
        not in text
    )


def test_bridge_imports_no_output_or_input_mode_enum():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    imported_names = {
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
        "VoiceInputMode"
        not in imported_names
    )

    assert (
        "VoiceOutputMode"
        not in imported_names
    )


def test_bridge_imports_no_transcript_type():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    imported_names = {
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
        "VoiceTranscript"
        not in imported_names
    )


def test_bridge_has_no_stt_provider_imports():
    text = MODULE.read_text().lower()

    for forbidden in (
        "speech_recognition",
        "whisper",
        "faster_whisper",
        "mlx_whisper",
        "speech-to-text",
    ):
        assert forbidden not in text


def test_bridge_has_no_network_imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    imported_roots = set()

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
            imported_roots.add(
                node.module.split(
                    ".",
                    1,
                )[0]
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            imported_roots.update(
                alias.name.split(
                    ".",
                    1,
                )[0]
                for alias in node.names
            )

    assert imported_roots.isdisjoint(
        {
            "requests",
            "httpx",
            "urllib",
            "socket",
            "aiohttp",
            "websockets",
        }
    )


def test_bridge_has_no_agent_memory_tool_imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

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


def test_bridge_has_no_ui_imports():
    text = MODULE.read_text()

    assert (
        "app.ui"
        not in text
    )


def test_bridge_has_no_avatar_symbols():
    text = MODULE.read_text()

    for forbidden in (
        "AvatarMode",
        "AvatarSnapshot",
        "KumaBodyState",
        "LISTENING",
    ):
        assert forbidden not in text


def test_window_does_not_wire_voice_state_bridge_yet():
    text = WINDOW.read_text()

    assert (
        "KumaVoiceStateBridge"
        not in text
    )

    assert (
        "voice_state_bridge"
        not in text
    )


def test_bridge_has_no_microphone_capture_calls():
    text = MODULE.read_text()

    for forbidden in (
        "start_capture(",
        "stop_capture(",
        "probe_availability(",
        "QAudioSource",
        "QMediaDevices",
        "readAll(",
        "readyRead",
    ):
        assert forbidden not in text


def test_bridge_has_no_playback_calls():
    text = MODULE.read_text()

    for forbidden in (
        "QProcess",
        "afplay",
        "/usr/bin/say",
        ".speak(",
        "speech_started.emit",
        "speech_finished.emit",
    ):
        assert forbidden not in text


def test_bridge_has_no_file_persistence_surface():
    text = MODULE.read_text()

    for forbidden in (
        "Path(",
        "open(",
        "write_text(",
        "write_bytes(",
        "sqlite",
        "tempfile",
    ):
        assert forbidden not in text


def test_bridge_has_no_background_loop_thread_or_timer():
    text = MODULE.read_text()

    for forbidden in (
        "QThread",
        "threading",
        "asyncio",
        "QTimer",
        "while True",
    ):
        assert forbidden not in text


def test_bridge_documents_independent_truth_ownership():
    text = MODULE.read_text()

    for required in (
        "INPUT OBSERVATION != OUTPUT STATE",
        "OUTPUT OBSERVATION != INPUT STATE",
        "INPUT UPDATE MUST PRESERVE OUTPUT TRUTH",
        "OUTPUT UPDATE MUST PRESERVE INPUT TRUTH",
        "BRIDGE AUTHORITY = NONE",
    ):
        assert required in text


def test_bridge_documents_no_avatar_projection():
    text = MODULE.read_text()

    assert (
        "BRIDGE SNAPSHOT != AVATAR STATE"
        in text
    )


def test_bridge_docs_no_authority_meaning():
    text = MODULE.read_text()

    for required in (
        "BRIDGE SNAPSHOT != COMMAND",
        "BRIDGE SNAPSHOT != PERMISSION",
        "BRIDGE SNAPSHOT != COGNITION",
    ):
        assert required in text


def test_source_references_are_private_read_only_handles():
    bridge, speech, microphone = make_bridge()

    assert (
        bridge._speech_controller
        is speech
    )

    assert (
        bridge._microphone_capture
        is microphone
    )


def test_bridge_does_not_emit_on_construction():
    speech = FakeSpeechSource()
    microphone = FakeMicrophoneSource()

    bridge = KumaVoiceStateBridge(
        speech,
        microphone,
    )

    events = events_from(
        bridge
    )

    assert events == []


def test_input_unavailable_and_output_error_can_coexist():
    bridge, speech, _ = make_bridge(
        input_state=input_observation(
            mode=VoiceInputMode.UNAVAILABLE
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.ERROR,
            reason="output failed",
        )
    )

    snapshot = bridge.voice_snapshot

    assert (
        snapshot.input_mode
        == VoiceInputMode.UNAVAILABLE
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.ERROR
    )


def test_input_error_and_output_idle_can_coexist():
    bridge, _, microphone = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.IDLE
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.ERROR,
            reason="input failed",
        )
    )

    snapshot = bridge.voice_snapshot

    assert (
        snapshot.input_mode
        == VoiceInputMode.ERROR
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.IDLE
    )


def test_synthesizing_output_does_not_claim_playback_after_input_update():
    bridge, _, microphone = make_bridge(
        output=output_snapshot(
            output=VoiceOutputMode.SYNTHESIZING
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING
        )
    )

    assert (
        bridge.voice_snapshot.output_mode
        == VoiceOutputMode.SYNTHESIZING
    )

    assert (
        bridge.voice_snapshot.playback_active
        is False
    )


def test_inactive_microphone_does_not_claim_capture_after_output_update():
    bridge, speech, _ = make_bridge(
        input_state=input_observation(
            mode=VoiceInputMode.INACTIVE
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        bridge.voice_snapshot.microphone_active
        is False
    )


def test_unavailable_microphone_does_not_claim_capture_after_output_update():
    bridge, speech, _ = make_bridge()

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING
        )
    )

    assert (
        bridge.voice_snapshot.input_mode
        == VoiceInputMode.UNAVAILABLE
    )

    assert (
        bridge.voice_snapshot.microphone_active
        is False
    )


def test_bridge_output_snapshot_remains_contract_valid_after_many_updates():
    bridge, speech, microphone = make_bridge()

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.INACTIVE,
            reason="ready",
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.SYNTHESIZING,
            reason="synth",
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING,
            reason="capture",
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="play",
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.IDLE,
            reason="done",
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.INACTIVE,
            reason="stop",
        )
    )

    snapshot = bridge.voice_snapshot

    assert isinstance(
        snapshot,
        VoiceSnapshot,
    )

    assert snapshot.authority == "NONE"

    assert (
        snapshot.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        snapshot.output_mode
        == VoiceOutputMode.IDLE
    )


def test_each_emitted_snapshot_has_none_authority():
    bridge, speech, microphone = make_bridge()

    events = events_from(
        bridge
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.INACTIVE,
            reason="ready",
        )
    )

    speech.publish(
        output_snapshot(
            output=VoiceOutputMode.PLAYING,
            reason="play",
        )
    )

    microphone.publish(
        input_observation(
            mode=VoiceInputMode.CAPTURING,
            reason="capture",
        )
    )

    assert events

    assert all(
        event.authority
        == "NONE"
        for event in events
    )


def test_bridge_has_no_authority_constructor_parameter():
    signature = inspect.signature(
        KumaVoiceStateBridge
    )

    assert (
        "authority"
        not in signature.parameters
    )


def test_bridge_has_no_permission_constructor_parameter():
    signature = inspect.signature(
        KumaVoiceStateBridge
    )

    assert (
        "permission"
        not in signature.parameters
    )


def test_bridge_has_no_execution_constructor_parameter():
    signature = inspect.signature(
        KumaVoiceStateBridge
    )

    assert (
        "executor"
        not in signature.parameters
    )


def test_bridge_module_compiles_as_plain_python_source():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
