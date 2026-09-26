from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

from app.voice.microphone_capture import (
    KumaMicrophoneCapture,
)
from app.voice.stt_audio_handoff import (
    STTAudioHandoffObservation,
    STTNativeAudioFormat,
)
from app.voice.voice_runtime import (
    VoiceInputMode,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

CAPTURE_MODULE = (
    ROOT
    / "app"
    / "voice"
    / "microphone_capture.py"
)


class FakeSignal:
    def __init__(
        self,
    ):
        self.callbacks = []

    def connect(
        self,
        callback,
    ):
        self.callbacks.append(
            callback
        )

    def emit(
        self,
        *args,
    ):
        for callback in tuple(
            self.callbacks
        ):
            callback(
                *args
            )


class FakeSampleFormat:
    name = "Float"


class NativeFormat:
    def __init__(
        self,
        *,
        rate=48000,
        channels=2,
        valid=True,
        metadata_error=False,
    ):
        self.rate = rate
        self.channels = channels
        self.valid = valid
        self.metadata_error = (
            metadata_error
        )

    def isValid(
        self,
    ):
        return self.valid

    def sampleRate(
        self,
    ):
        if self.metadata_error:
            raise RuntimeError(
                "synthetic format failure"
            )
        return self.rate

    def channelCount(
        self,
    ):
        if self.metadata_error:
            raise RuntimeError(
                "synthetic format failure"
            )
        return self.channels

    def sampleFormat(
        self,
    ):
        if self.metadata_error:
            raise RuntimeError(
                "synthetic format failure"
            )
        return FakeSampleFormat()


class LegacyFormat:
    """
    Old Voice-1C validity-only format surface.

    With no consumer configured, STT metadata must not be queried.
    """

    def isValid(
        self,
    ):
        return True


class FakeDevice:
    def __init__(
        self,
        audio_format,
    ):
        self.audio_format = (
            audio_format
        )

    def isNull(
        self,
    ):
        return False

    def preferredFormat(
        self,
    ):
        return self.audio_format

    def description(
        self,
    ):
        return "STT-1B Test Microphone"


class FakeIODevice:
    def __init__(
        self,
        chunks=None,
    ):
        self.readyRead = (
            FakeSignal()
        )
        self.chunks = list(
            chunks
            or []
        )
        self.closed = False

    def readAll(
        self,
    ):
        if not self.chunks:
            return b""

        return self.chunks.pop(
            0
        )

    def push(
        self,
        payload,
    ):
        self.chunks.append(
            payload
        )
        self.readyRead.emit()

    def close(
        self,
    ):
        self.closed = True


class FakeSource:
    def __init__(
        self,
        io_device,
    ):
        self.stateChanged = (
            FakeSignal()
        )
        self.io_device = (
            io_device
        )
        self.start_count = 0
        self.stop_count = 0

    def start(
        self,
    ):
        self.start_count += 1
        return self.io_device

    def stop(
        self,
    ):
        self.stop_count += 1


class RecordingFactory:
    def __init__(
        self,
        source,
    ):
        self.source = source
        self.calls = []

    def __call__(
        self,
        device,
        audio_format,
        parent,
    ):
        self.calls.append(
            (
                device,
                audio_format,
                parent,
            )
        )
        return self.source


def make_controller(
    *,
    audio_format=None,
    chunks=None,
    consumer=None,
):
    selected_format = (
        audio_format
        if audio_format is not None
        else NativeFormat()
    )

    device = FakeDevice(
        selected_format
    )

    io_device = FakeIODevice(
        chunks
    )

    source = FakeSource(
        io_device
    )

    factory = RecordingFactory(
        source
    )

    controller = (
        KumaMicrophoneCapture(
            device_provider=lambda:
            device,
            source_factory=factory,
            audio_consumer=consumer,
        )
    )

    return (
        controller,
        device,
        selected_format,
        io_device,
        source,
        factory,
    )


def test_stt_1b_adds_only_optional_constructor_consumer():
    signature = (
        inspect.signature(
            KumaMicrophoneCapture
        )
    )

    parameter = (
        signature.parameters[
            "audio_consumer"
        ]
    )

    assert (
        parameter.default
        is None
    )


def test_non_callable_audio_consumer_is_rejected():
    with pytest.raises(
        TypeError,
        match="audio_consumer",
    ):
        KumaMicrophoneCapture(
            audio_consumer=object(),
        )


def test_default_none_consumer_preserves_legacy_format_surface():
    (
        controller,
        _,
        _,
        io_device,
        _,
        _,
    ) = make_controller(
        audio_format=LegacyFormat(),
        consumer=None,
    )

    assert (
        controller.start_capture()
        is True
    )

    io_device.push(
        b"legacy"
    )

    assert (
        controller.bytes_observed
        == 6
    )

    assert (
        controller.observation.input_mode
        is VoiceInputMode.CAPTURING
    )


def test_preferred_format_identity_remains_capture_authority():
    (
        controller,
        device,
        audio_format,
        _,
        _,
        factory,
    ) = make_controller()

    controller.start_capture()

    assert len(
        factory.calls
    ) == 1

    passed_device, passed_format, parent = (
        factory.calls[0]
    )

    assert (
        passed_device
        is device
    )

    assert (
        passed_format
        is audio_format
    )

    assert (
        parent
        is controller
    )


def test_nonempty_payload_is_delivered_exactly_once():
    calls = []

    def consumer(
        payload,
        audio_format,
    ):
        calls.append(
            (
                payload,
                audio_format,
            )
        )

    (
        controller,
        _,
        _,
        io_device,
        _,
        _,
    ) = make_controller(
        consumer=consumer,
    )

    controller.start_capture()

    payload = b"\x01\x02\x03\x04"

    io_device.push(
        payload
    )

    assert len(
        calls
    ) == 1

    observed_payload, observed_format = (
        calls[0]
    )

    assert (
        observed_payload
        is payload
    )

    assert isinstance(
        observed_format,
        STTNativeAudioFormat,
    )

    assert (
        observed_format.sample_rate_hz
        == 48000
    )

    assert (
        observed_format.channel_count
        == 2
    )

    assert (
        observed_format.sample_format
        == "Float"
    )


def test_immediately_available_bytes_use_same_handoff():
    calls = []

    (
        controller,
        _,
        _,
        _,
        _,
        _,
    ) = make_controller(
        chunks=[
            b"immediate"
        ],
        consumer=lambda payload, fmt:
        calls.append(
            (
                payload,
                fmt,
            )
        ),
    )

    controller.start_capture()

    assert len(
        calls
    ) == 1

    assert (
        calls[0][0]
        == b"immediate"
    )


def test_capture_truth_is_established_before_consumer_runs():
    observed_modes = []

    controller = None

    def consumer(
        _payload,
        _format,
    ):
        observed_modes.append(
            controller.observation.input_mode
        )

    (
        controller,
        _,
        _,
        io_device,
        _,
        _,
    ) = make_controller(
        consumer=consumer,
    )

    controller.start_capture()

    io_device.push(
        b"truth-first"
    )

    assert observed_modes == [
        VoiceInputMode.CAPTURING
    ]


def test_consumer_failure_does_not_fail_microphone_capture():
    errors = []

    def consumer(
        _payload,
        _format,
    ):
        raise RuntimeError(
            "synthetic STT failure"
        )

    (
        controller,
        _,
        _,
        io_device,
        _,
        _,
    ) = make_controller(
        consumer=consumer,
    )

    controller.capture_error.connect(
        errors.append
    )

    controller.start_capture()

    io_device.push(
        b"still-capture"
    )

    assert errors == []

    assert (
        controller.observation.input_mode
        is VoiceInputMode.CAPTURING
    )

    assert (
        controller.bytes_observed
        == len(
            b"still-capture"
        )
    )


def test_metadata_failure_does_not_fail_microphone_capture():
    calls = []
    errors = []

    (
        controller,
        _,
        _,
        io_device,
        _,
        _,
    ) = make_controller(
        audio_format=NativeFormat(
            metadata_error=True
        ),
        consumer=lambda *args:
        calls.append(
            args
        ),
    )

    controller.capture_error.connect(
        errors.append
    )

    controller.start_capture()

    io_device.push(
        b"native"
    )

    assert calls == []
    assert errors == []

    assert (
        controller.observation.input_mode
        is VoiceInputMode.CAPTURING
    )

    assert (
        controller.bytes_observed
        == 6
    )


def test_capture_controller_does_not_retain_raw_payload():
    payload = b"private-stt-1b-audio"

    (
        controller,
        _,
        _,
        io_device,
        _,
        _,
    ) = make_controller(
        consumer=lambda *_args:
        None,
    )

    controller.start_capture()

    io_device.push(
        payload
    )

    assert (
        payload
        not in tuple(
            controller.__dict__.values()
        )
    )


def test_capture_controller_does_not_retain_handoff_observation():
    (
        controller,
        _,
        _,
        io_device,
        _,
        _,
    ) = make_controller(
        consumer=lambda *_args:
        None,
    )

    controller.start_capture()

    io_device.push(
        b"observation"
    )

    assert not any(
        isinstance(
            value,
            STTAudioHandoffObservation,
        )
        for value
        in controller.__dict__.values()
    )


def test_stale_ready_read_after_stop_cannot_reach_consumer():
    calls = []

    (
        controller,
        _,
        _,
        io_device,
        _,
        _,
    ) = make_controller(
        consumer=lambda payload, _fmt:
        calls.append(
            payload
        ),
    )

    controller.start_capture()

    controller.stop_capture()

    io_device.push(
        b"stale"
    )

    assert calls == []


def test_capture_module_uses_only_frozen_stt_1a_seam():
    tree = ast.parse(
        CAPTURE_MODULE.read_text(),
        filename=str(
            CAPTURE_MODULE
        ),
    )

    imported_modules = {
        node.module
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            ast.ImportFrom,
        )
        and node.module
    }

    assert (
        "app.voice.stt_audio_handoff"
        in imported_modules
    )

    forbidden_prefixes = (
        "app.agent",
        "app.memory",
        "app.realtime",
        "app.integration",
    )

    assert all(
        not module.startswith(
            forbidden_prefixes
        )
        for module
        in imported_modules
    )


def test_capture_module_does_not_normalize_or_force_qt_format():
    source = (
        CAPTURE_MODULE.read_text()
    )

    assert (
        "device.preferredFormat()"
        in source
    )

    for forbidden in (
        "setSampleRate(",
        "setChannelCount(",
        "setSampleFormat(",
    ):
        assert (
            forbidden
            not in source
        )


def test_ready_read_orders_truth_before_ephemeral_handoff():
    source = (
        CAPTURE_MODULE.read_text()
    )

    tree = ast.parse(
        source,
        filename=str(
            CAPTURE_MODULE
        ),
    )

    capture_class = next(
        node
        for node in tree.body
        if isinstance(
            node,
            ast.ClassDef,
        )
        and node.name
        == "KumaMicrophoneCapture"
    )

    method = next(
        node
        for node in capture_class.body
        if isinstance(
            node,
            ast.FunctionDef,
        )
        and node.name
        == "_on_ready_read"
    )

    lines = source.splitlines()

    block = "\n".join(
        lines[
            method.lineno - 1:
            method.end_lineno
        ]
    )

    assert (
        block.index(
            "self._bytes_observed"
        )
        < block.index(
            "VoiceInputMode.CAPTURING"
        )
        < block.index(
            "self._offer_audio_to_stt"
        )
    )


def test_stt_1b_creates_no_transcript_user_turn_or_model_surface():
    source = (
        CAPTURE_MODULE.read_text()
    )

    for forbidden in (
        "VoiceTranscript(",
        "KumaGUIRuntime",
        "KumaAgent",
        "MissionService",
        "QProcess",
        "subprocess",
        "whisper",
        "speech_recognition",
        "faster_whisper",
        "mlx_whisper",
    ):
        assert (
            forbidden
            not in source
        )
