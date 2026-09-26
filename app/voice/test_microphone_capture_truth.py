from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path

import pytest

from PySide6.QtMultimedia import (
    QAudio,
    QAudioSource,
    QMediaDevices,
)

from app.voice.microphone_capture import (
    KumaMicrophoneCapture,
    MicrophoneCaptureObservation,
)
from app.voice.voice_runtime import (
    VOICE_REASON_MAX_CHARS,
    VoiceInputMode,
)


MODULE = Path(
    "app/voice/microphone_capture.py"
)

WINDOW = Path(
    "app/ui/window.py"
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


class FakeFormat:
    def __init__(
        self,
        *,
        valid=True,
    ):
        self.valid = valid

    def isValid(
        self,
    ):
        return self.valid


class FakeDevice:
    def __init__(
        self,
        *,
        null=False,
        valid_format=True,
        description="Test Microphone",
        format_error=False,
        description_error=False,
    ):
        self.null = null
        self.audio_format = (
            FakeFormat(
                valid=valid_format
            )
        )
        self.description_value = (
            description
        )
        self.format_error = (
            format_error
        )
        self.description_error = (
            description_error
        )

    def isNull(
        self,
    ):
        return self.null

    def preferredFormat(
        self,
    ):
        if self.format_error:
            raise RuntimeError(
                "format failure"
            )

        return self.audio_format

    def description(
        self,
    ):
        if self.description_error:
            raise RuntimeError(
                "description failure"
            )

        return (
            self.description_value
        )


class FakeIODevice:
    def __init__(
        self,
        chunks=None,
        *,
        read_error=False,
    ):
        self.readyRead = (
            FakeSignal()
        )

        self.chunks = list(
            chunks
            or []
        )

        self.read_error = (
            read_error
        )

        self.closed = False
        self.read_count = 0

    def readAll(
        self,
    ):
        self.read_count += 1

        if self.read_error:
            raise RuntimeError(
                "read failed"
            )

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
        io_device=None,
        *,
        error_value=QAudio.Error.NoError,
        start_error=False,
        start_none=False,
        emit_stopped_on_stop=False,
    ):
        self.stateChanged = (
            FakeSignal()
        )

        self.io_device = (
            io_device
            if io_device is not None
            else FakeIODevice()
        )

        self.error_value = (
            error_value
        )

        self.start_error = (
            start_error
        )

        self.start_none = (
            start_none
        )

        self.emit_stopped_on_stop = (
            emit_stopped_on_stop
        )

        self.start_count = 0
        self.stop_count = 0

    def start(
        self,
    ):
        self.start_count += 1

        if self.start_error:
            raise RuntimeError(
                "start failed"
            )

        if self.start_none:
            return None

        return self.io_device

    def stop(
        self,
    ):
        self.stop_count += 1

        if self.emit_stopped_on_stop:
            self.stateChanged.emit(
                QAudio.State.StoppedState
            )

    def error(
        self,
    ):
        return self.error_value

    def emit_state(
        self,
        state,
    ):
        self.stateChanged.emit(
            state
        )


class Factory:
    def __init__(
        self,
        sources,
    ):
        self.sources = list(
            sources
        )
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

        if not self.sources:
            raise RuntimeError(
                "no source queued"
            )

        value = self.sources.pop(
            0
        )

        if isinstance(
            value,
            BaseException,
        ):
            raise value

        return value


def make_controller(
    *,
    device=None,
    source=None,
    device_provider=None,
    source_factory=None,
):
    selected_device = (
        device
        if device is not None
        else FakeDevice()
    )

    selected_source = (
        source
        if source is not None
        else FakeSource()
    )

    provider = (
        device_provider
        if device_provider is not None
        else lambda:
        selected_device
    )

    factory = (
        source_factory
        if source_factory is not None
        else Factory(
            [
                selected_source
            ]
        )
    )

    controller = (
        KumaMicrophoneCapture(
            device_provider=provider,
            source_factory=factory,
        )
    )

    return (
        controller,
        selected_device,
        selected_source,
        factory,
    )


def state_events(
    controller,
):
    events = []

    controller.capture_state_changed.connect(
        events.append
    )

    return events


def error_events(
    controller,
):
    events = []

    controller.capture_error.connect(
        events.append
    )

    return events


def method_source(
    name,
):
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
            == "KumaMicrophoneCapture"
        )
    )

    method = next(
        node
        for node in cls.body
        if (
            isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
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


def test_observation_defaults_to_unavailable():
    value = (
        MicrophoneCaptureObservation()
    )

    assert (
        value.input_mode
        == VoiceInputMode.UNAVAILABLE
    )

    assert (
        value.microphone_active
        is False
    )

    assert value.reason == ""
    assert value.authority == "NONE"


@pytest.mark.parametrize(
    "mode",
    (
        VoiceInputMode.UNAVAILABLE,
        VoiceInputMode.INACTIVE,
        VoiceInputMode.ERROR,
    ),
)
def test_noncapturing_observation_requires_false_active(
    mode,
):
    value = (
        MicrophoneCaptureObservation(
            input_mode=mode,
            microphone_active=False,
        )
    )

    assert (
        value.microphone_active
        is False
    )


def test_capturing_observation_requires_true_active():
    value = (
        MicrophoneCaptureObservation(
            input_mode=(
                VoiceInputMode.CAPTURING
            ),
            microphone_active=True,
        )
    )

    assert (
        value.microphone_active
        is True
    )


@pytest.mark.parametrize(
    (
        "mode",
        "active",
    ),
    (
        (
            VoiceInputMode.CAPTURING,
            False,
        ),
        (
            VoiceInputMode.INACTIVE,
            True,
        ),
        (
            VoiceInputMode.ERROR,
            True,
        ),
        (
            VoiceInputMode.UNAVAILABLE,
            True,
        ),
    ),
)
def test_observation_rejects_false_capture_truth(
    mode,
    active,
):
    with pytest.raises(
        ValueError,
        match="microphone_active",
    ):
        MicrophoneCaptureObservation(
            input_mode=mode,
            microphone_active=active,
        )


def test_observation_rejects_transcribing():
    with pytest.raises(
        ValueError,
        match="observations",
    ):
        MicrophoneCaptureObservation(
            input_mode=(
                VoiceInputMode.TRANSCRIBING
            ),
            microphone_active=False,
        )


def test_observation_rejects_non_enum_mode():
    with pytest.raises(
        TypeError,
        match="VoiceInputMode",
    ):
        MicrophoneCaptureObservation(
            input_mode="capturing",
            microphone_active=False,
        )


@pytest.mark.parametrize(
    "active",
    (
        1,
        0,
        "true",
        None,
    ),
)
def test_observation_requires_strict_bool(
    active,
):
    with pytest.raises(
        TypeError,
        match="bool",
    ):
        MicrophoneCaptureObservation(
            microphone_active=active,
        )


def test_observation_reason_normalizes_whitespace():
    value = (
        MicrophoneCaptureObservation(
            reason="  microphone\n  ready\t now  "
        )
    )

    assert (
        value.reason
        == "microphone ready now"
    )


def test_observation_reason_enforces_voice_bound():
    with pytest.raises(
        ValueError,
        match=str(
            VOICE_REASON_MAX_CHARS
        ),
    ):
        MicrophoneCaptureObservation(
            reason=(
                "x"
                * (
                    VOICE_REASON_MAX_CHARS
                    + 1
                )
            )
        )


def test_observation_reason_requires_string():
    with pytest.raises(
        TypeError,
        match="reason",
    ):
        MicrophoneCaptureObservation(
            reason=None,
        )


def test_observation_is_frozen():
    value = (
        MicrophoneCaptureObservation()
    )

    with pytest.raises(
        FrozenInstanceError
    ):
        value.reason = "changed"


def test_observation_authority_is_not_constructor_input():
    with pytest.raises(
        TypeError
    ):
        MicrophoneCaptureObservation(
            authority="FULL"
        )


def test_controller_begins_without_fabricating_microphone():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    assert (
        controller.observation.input_mode
        == VoiceInputMode.UNAVAILABLE
    )

    assert (
        controller.observation.microphone_active
        is False
    )

    assert (
        controller.capture_requested
        is False
    )

    assert (
        controller.bytes_observed
        == 0
    )


def test_constructor_does_not_probe_device():
    calls = []

    def provider():
        calls.append(
            True
        )
        return FakeDevice()

    KumaMicrophoneCapture(
        device_provider=provider,
        source_factory=lambda *args:
        FakeSource(),
    )

    assert calls == []


def test_probe_available_device_becomes_inactive():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    assert (
        controller.probe_availability()
        is True
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        controller.observation.microphone_active
        is False
    )

    assert (
        controller.device_available
        is True
    )


def test_probe_records_device_description():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        device=FakeDevice(
            description="MacBook Air Microphone"
        )
    )

    controller.probe_availability()

    assert (
        controller.device_description
        == "MacBook Air Microphone"
    )


def test_description_failure_does_not_fake_unavailability():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        device=FakeDevice(
            description_error=True
        )
    )

    assert (
        controller.probe_availability()
        is True
    )

    assert (
        controller.device_available
        is True
    )

    assert (
        controller.device_description
        == ""
    )


def test_probe_null_device_remains_unavailable():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        device=FakeDevice(
            null=True
        )
    )

    assert (
        controller.probe_availability()
        is False
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.UNAVAILABLE
    )

    assert (
        controller.observation.microphone_active
        is False
    )


def test_probe_invalid_format_remains_unavailable():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        device=FakeDevice(
            valid_format=False
        )
    )

    assert (
        controller.probe_availability()
        is False
    )

    assert (
        controller.device_available
        is False
    )


def test_probe_format_exception_remains_unavailable():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        device=FakeDevice(
            format_error=True
        )
    )

    assert (
        controller.probe_availability()
        is False
    )

    assert (
        controller.device_available
        is False
    )


def test_probe_provider_exception_remains_unavailable():
    def provider():
        raise RuntimeError(
            "discovery failed"
        )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        device_provider=provider
    )

    assert (
        controller.probe_availability()
        is False
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.UNAVAILABLE
    )


def test_start_request_does_not_claim_capturing():
    source = FakeSource(
        FakeIODevice()
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    assert (
        controller.start_capture()
        is True
    )

    assert (
        controller.capture_requested
        is True
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        controller.observation.microphone_active
        is False
    )


def test_start_calls_native_source_once():
    source = FakeSource()

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    assert (
        source.start_count
        == 1
    )


def test_source_factory_receives_device_format_and_controller_parent():
    device = FakeDevice()
    source = FakeSource()
    factory = Factory(
        [
            source
        ]
    )

    controller = (
        KumaMicrophoneCapture(
            device_provider=lambda:
            device,
            source_factory=factory,
        )
    )

    controller.start_capture()

    assert (
        len(
            factory.calls
        )
        == 1
    )

    passed_device, passed_format, parent = (
        factory.calls[0]
    )

    assert (
        passed_device
        is device
    )

    assert (
        passed_format
        is device.audio_format
    )

    assert (
        parent
        is controller
    )


def test_duplicate_start_is_rejected_without_second_native_start():
    source = FakeSource()

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    assert (
        controller.start_capture()
        is True
    )

    assert (
        controller.start_capture()
        is False
    )

    assert (
        source.start_count
        == 1
    )


def test_empty_ready_read_does_not_claim_capturing():
    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    io_device.push(
        b""
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        controller.bytes_observed
        == 0
    )


def test_first_nonempty_audio_bytes_prove_capturing():
    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    io_device.push(
        b"\x01\x02\x03\x04"
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        controller.observation.microphone_active
        is True
    )

    assert (
        controller.bytes_observed
        == 4
    )


def test_immediately_available_nonempty_bytes_prove_capture_during_start():
    io_device = FakeIODevice(
        [
            b"\x01\x02"
        ]
    )

    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    assert (
        controller.start_capture()
        is True
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.CAPTURING
    )

    assert (
        controller.bytes_observed
        == 2
    )


def test_active_qaudio_state_without_bytes_does_not_prove_capture():
    source = FakeSource(
        FakeIODevice()
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    source.emit_state(
        QAudio.State.ActiveState
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        controller.observation.microphone_active
        is False
    )


def test_idle_qaudio_state_without_bytes_does_not_prove_capture():
    source = FakeSource(
        FakeIODevice()
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    source.emit_state(
        QAudio.State.IdleState
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )


def test_additional_audio_accumulates_count_without_republishing_capturing():
    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    events = state_events(
        controller
    )

    controller.start_capture()

    io_device.push(
        b"12"
    )

    capturing_events_before = [
        event
        for event in events
        if (
            event.input_mode
            == VoiceInputMode.CAPTURING
        )
    ]

    io_device.push(
        b"345"
    )

    capturing_events_after = [
        event
        for event in events
        if (
            event.input_mode
            == VoiceInputMode.CAPTURING
        )
    ]

    assert (
        controller.bytes_observed
        == 5
    )

    assert (
        len(
            capturing_events_before
        )
        == 1
    )

    assert (
        len(
            capturing_events_after
        )
        == 1
    )


def test_raw_audio_bytes_are_not_retained_on_controller():
    payload = (
        b"private-microphone-audio"
    )

    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    io_device.push(
        payload
    )

    values = tuple(
        controller.__dict__.values()
    )

    assert (
        payload
        not in values
    )

    assert (
        controller.bytes_observed
        == len(payload)
    )


def test_stop_after_capture_returns_inactive():
    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    io_device.push(
        b"1234"
    )

    assert (
        controller.stop_capture()
        is True
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        controller.observation.microphone_active
        is False
    )


def test_stop_before_first_bytes_returns_inactive():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    controller.start_capture()

    assert (
        controller.stop_capture()
        is True
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )


def test_stop_calls_source_stop_and_io_close():
    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()
    controller.stop_capture()

    assert (
        source.stop_count
        == 1
    )

    assert (
        io_device.closed
        is True
    )


def test_stop_invalidates_synchronous_native_stopped_signal():
    io_device = FakeIODevice()

    source = FakeSource(
        io_device,
        emit_stopped_on_stop=True,
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    errors = error_events(
        controller
    )

    controller.start_capture()

    io_device.push(
        b"12"
    )

    controller.stop_capture()

    assert errors == []

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )


def test_idle_stop_is_noop():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    events = state_events(
        controller
    )

    assert (
        controller.stop_capture()
        is False
    )

    assert events == []


def test_close_stops_active_capture():
    source = FakeSource()

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()
    controller.close()

    assert (
        source.stop_count
        == 1
    )

    assert (
        controller.capture_requested
        is False
    )


def test_source_creation_failure_publishes_error():
    factory = Factory(
        [
            RuntimeError(
                "factory failed"
            )
        ]
    )

    controller = (
        KumaMicrophoneCapture(
            device_provider=lambda:
            FakeDevice(),
            source_factory=factory,
        )
    )

    errors = error_events(
        controller
    )

    assert (
        controller.start_capture()
        is False
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.ERROR
    )

    assert (
        controller.observation.microphone_active
        is False
    )

    assert len(errors) == 1


def test_none_source_publishes_error():
    controller = (
        KumaMicrophoneCapture(
            device_provider=lambda:
            FakeDevice(),
            source_factory=lambda *args:
            None,
        )
    )

    assert (
        controller.start_capture()
        is False
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.ERROR
    )


def test_native_start_exception_publishes_error_and_stops_source():
    source = FakeSource(
        start_error=True
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    assert (
        controller.start_capture()
        is False
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.ERROR
    )

    assert (
        source.stop_count
        == 1
    )


def test_native_start_returning_none_publishes_error():
    source = FakeSource(
        start_none=True
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    assert (
        controller.start_capture()
        is False
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.ERROR
    )


def test_audio_read_failure_publishes_error_and_closes_session():
    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    errors = error_events(
        controller
    )

    controller.start_capture()

    io_device.read_error = True
    io_device.readyRead.emit()

    assert (
        controller.observation.input_mode
        == VoiceInputMode.ERROR
    )

    assert (
        controller.observation.microphone_active
        is False
    )

    assert (
        controller.capture_requested
        is False
    )

    assert (
        source.stop_count
        == 1
    )

    assert (
        io_device.closed
        is True
    )

    assert len(errors) == 1


@pytest.mark.parametrize(
    "error",
    (
        QAudio.Error.OpenError,
        QAudio.Error.IOError,
        QAudio.Error.UnderrunError,
        QAudio.Error.FatalError,
    ),
)
def test_stopped_state_with_native_error_publishes_error(
    error,
):
    source = FakeSource(
        error_value=error
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    source.emit_state(
        QAudio.State.StoppedState
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.ERROR
    )

    assert (
        controller.observation.microphone_active
        is False
    )


def test_unexpected_stopped_state_without_native_error_is_error():
    source = FakeSource()

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    source.emit_state(
        QAudio.State.StoppedState
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.ERROR
    )

    assert (
        "unexpectedly"
        in controller.observation.reason
    )


def test_stale_ready_read_after_stop_cannot_reactivate_microphone():
    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    callbacks = tuple(
        io_device.readyRead.callbacks
    )

    controller.stop_capture()

    io_device.chunks.append(
        b"late"
    )

    for callback in callbacks:
        callback()

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        controller.observation.microphone_active
        is False
    )


def test_stale_state_signal_after_stop_cannot_publish_error():
    source = FakeSource()

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    callbacks = tuple(
        source.stateChanged.callbacks
    )

    controller.stop_capture()

    source.error_value = (
        QAudio.Error.FatalError
    )

    for callback in callbacks:
        callback(
            QAudio.State.StoppedState
        )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )


def test_bytes_observed_resets_on_new_session():
    first_io = FakeIODevice()
    second_io = FakeIODevice()

    first_source = FakeSource(
        first_io
    )

    second_source = FakeSource(
        second_io
    )

    factory = Factory(
        [
            first_source,
            second_source,
        ]
    )

    controller = (
        KumaMicrophoneCapture(
            device_provider=lambda:
            FakeDevice(),
            source_factory=factory,
        )
    )

    controller.start_capture()

    first_io.push(
        b"12345"
    )

    assert (
        controller.bytes_observed
        == 5
    )

    controller.stop_capture()

    controller.start_capture()

    assert (
        controller.bytes_observed
        == 0
    )

    second_io.push(
        b"12"
    )

    assert (
        controller.bytes_observed
        == 2
    )


def test_probe_during_active_request_does_not_requery_device():
    calls = []

    device = FakeDevice()

    def provider():
        calls.append(
            True
        )
        return device

    controller = (
        KumaMicrophoneCapture(
            device_provider=provider,
            source_factory=Factory(
                [
                    FakeSource()
                ]
            ),
        )
    )

    controller.start_capture()

    before = len(
        calls
    )

    assert (
        controller.probe_availability()
        is True
    )

    assert (
        len(
            calls
        )
        == before
    )


def test_publish_derives_active_flag_only_from_capturing():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    for mode in (
        VoiceInputMode.UNAVAILABLE,
        VoiceInputMode.INACTIVE,
        VoiceInputMode.ERROR,
    ):
        result = controller._publish(
            mode,
            reason=mode.value,
        )

        assert (
            result.microphone_active
            is False
        )

    result = controller._publish(
        VoiceInputMode.CAPTURING,
        reason="bytes observed",
    )

    assert (
        result.microphone_active
        is True
    )


def test_publish_does_not_accept_microphone_active_input():
    signature = inspect.signature(
        KumaMicrophoneCapture._publish
    )

    assert (
        "microphone_active"
        not in signature.parameters
    )


def test_publish_does_not_accept_authority_input():
    signature = inspect.signature(
        KumaMicrophoneCapture._publish
    )

    assert (
        "authority"
        not in signature.parameters
    )


def test_every_published_observation_has_zero_authority():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    events = state_events(
        controller
    )

    controller.probe_availability()
    controller.start_capture()

    controller._io_device.push(
        b"1"
    )

    controller.stop_capture()

    assert events

    assert all(
        event.authority
        == "NONE"
        for event in events
    )


def test_capture_error_never_changes_authority():
    source = FakeSource(
        error_value=(
            QAudio.Error.FatalError
        )
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    source.emit_state(
        QAudio.State.StoppedState
    )

    assert (
        controller.observation.authority
        == "NONE"
    )


def test_start_capture_ast_has_no_capturing_publication():
    method = method_source(
        "start_capture"
    )

    tree = ast.parse(
        method
    )

    capturing_attributes = [
        node
        for node in ast.walk(
            tree
        )
        if (
            isinstance(
                node,
                ast.Attribute,
            )
            and node.attr
            == "CAPTURING"
        )
    ]

    assert capturing_attributes == []


def test_ready_read_is_only_live_capturing_publication_site():
    module_text = MODULE.read_text()

    assert (
        module_text.count(
            "VoiceInputMode.CAPTURING"
        )
        >= 3
    )

    method = method_source(
        "_on_ready_read"
    )

    assert (
        "VoiceInputMode.CAPTURING"
        in method
    )

    start = method_source(
        "start_capture"
    )

    assert (
        "VoiceInputMode.CAPTURING"
        not in start
    )


def test_ready_read_requires_nonempty_payload_before_capturing():
    method = method_source(
        "_on_ready_read"
    )

    assert (
        method.index(
            "if not payload:"
        )
        < method.index(
            "VoiceInputMode.CAPTURING"
        )
    )


def test_ready_read_discards_raw_payload_after_counting():
    method = method_source(
        "_on_ready_read"
    )

    assert (
        "self._bytes_observed"
        in method
    )

    assert (
        "self._audio"
        not in method
    )

    assert (
        "self._buffer"
        not in method
    )

    assert (
        "write("
        not in method
    )


def test_stop_invalidates_generation_before_native_stop():
    method = method_source(
        "stop_capture"
    )

    assert (
        method.index(
            "self._generation += 1"
        )
        < method.index(
            "source.stop()"
        )
    )


def test_stop_publishes_terminal_state_after_native_stop_and_close():
    method = method_source(
        "stop_capture"
    )

    publish_index = method.rindex(
        "self._publish("
    )

    assert (
        method.index(
            "source.stop()"
        )
        < publish_index
    )

    assert (
        method.index(
            "io_device.close()"
        )
        < publish_index
    )


def test_failure_invalidates_generation_before_native_stop():
    method = method_source(
        "_fail_current_session"
    )

    assert (
        method.index(
            "self._generation += 1"
        )
        < method.index(
            "source.stop()"
        )
    )


def test_module_uses_existing_qt_multimedia_capture_backend():
    text = MODULE.read_text()

    for required in (
        "QAudioSource",
        "QMediaDevices",
        "defaultAudioInput",
        "preferredFormat",
        "readyRead",
        "readAll",
    ):
        assert required in text


def test_default_source_factory_constructs_qaudio_source():
    method = method_source(
        "_default_source_factory"
    )

    assert (
        "QAudioSource("
        in method
    )


def test_module_has_no_stt_provider_imports():
    text = MODULE.read_text().lower()

    for forbidden in (
        "speech_recognition",
        "faster_whisper",
        "mlx_whisper",
        "openai",
        "google.genai",
        "speech-to-text",
    ):
        assert forbidden not in text


def test_module_has_no_agent_memory_or_tool_imports():
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

    assert not any(
        name.startswith(
            "app.agent"
        )
        for name in modules
    )

    assert not any(
        name.startswith(
            "app.memory"
        )
        for name in modules
    )

    assert not any(
        name.startswith(
            "app.tools"
        )
        for name in modules
    )


def test_module_has_no_network_imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    forbidden = {
        "requests",
        "httpx",
        "urllib",
        "socket",
        "aiohttp",
        "websockets",
    }

    imported = set()

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
            imported.add(
                node.module.split(
                    ".",
                    1,
                )[0]
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            imported.update(
                alias.name.split(
                    ".",
                    1,
                )[0]
                for alias in node.names
            )

    assert (
        imported
        .isdisjoint(
            forbidden
        )
    )


def test_module_has_no_file_persistence_import():
    text = MODULE.read_text()

    assert (
        "from pathlib import"
        not in text
    )

    assert (
        "import sqlite"
        not in text
    )


def test_module_has_no_background_thread_or_timer():
    text = MODULE.read_text()

    for forbidden in (
        "QThread",
        "threading",
        "QTimer",
        "asyncio",
        "while True",
    ):
        assert forbidden not in text


def test_module_does_not_import_avatar_or_window():
    text = MODULE.read_text()

    assert (
        "app.ui"
        not in text
    )

    assert (
        "Avatar"
        not in text
    )


def test_window_does_not_wire_voice_1c_yet():
    text = WINDOW.read_text()

    assert (
        "KumaMicrophoneCapture"
        not in text
    )

    assert (
        "microphone_capture"
        not in text
    )


def test_voice_1c_module_does_not_publish_listening_avatar_state():
    text = MODULE.read_text()

    assert (
        "AvatarMode.LISTENING"
        not in text
    )

    assert (
        "KumaBodyState.LISTENING"
        not in text
    )


def test_voice_1c_has_no_transcript_type_dependency():
    text = MODULE.read_text()

    assert (
        "VoiceTranscript"
        not in text
    )


def test_voice_1c_has_no_voice_output_mode_dependency():
    text = MODULE.read_text()

    assert (
        "VoiceOutputMode"
        not in text
    )


def test_voice_1c_does_not_mutate_unified_voice_snapshot():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(MODULE),
    )

    imported_names = set()

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.ImportFrom,
        ):
            imported_names.update(
                alias.asname
                or alias.name
                for alias in node.names
            )

        elif isinstance(
            node,
            ast.Import,
        ):
            imported_names.update(
                alias.asname
                or alias.name
                for alias in node.names
            )

    referenced_names = {
        node.id
        for node in ast.walk(
            tree
        )
        if isinstance(
            node,
            ast.Name,
        )
    }

    assert (
        "VoiceSnapshot"
        not in imported_names
    )

    assert (
        "VoiceSnapshot"
        not in referenced_names
    )


def test_voice_1c_documents_request_not_active_boundary():
    text = MODULE.read_text()

    for required in (
        "MICROPHONE REQUEST != MICROPHONE ACTIVE",
        "DEVICE AVAILABLE != CAPTURING",
        "QAudioSource.start() CALLED != CAPTURING",
        "FIRST NON-EMPTY AUDIO BYTES == CAPTURE EVIDENCE",
        "MICROPHONE AUTHORITY = NONE",
    ):
        assert required in text


def test_capture_requested_property_has_no_setter():
    descriptor = (
        KumaMicrophoneCapture
        .capture_requested
    )

    assert isinstance(
        descriptor,
        property,
    )

    assert (
        descriptor.fset
        is None
    )


def test_bytes_observed_property_has_no_setter():
    descriptor = (
        KumaMicrophoneCapture
        .bytes_observed
    )

    assert isinstance(
        descriptor,
        property,
    )

    assert (
        descriptor.fset
        is None
    )


def test_observation_property_has_no_setter():
    descriptor = (
        KumaMicrophoneCapture
        .observation
    )

    assert isinstance(
        descriptor,
        property,
    )

    assert (
        descriptor.fset
        is None
    )


def test_default_qt_api_symbols_exist():
    assert (
        QAudioSource
        is not None
    )

    assert (
        QMediaDevices
        is not None
    )

    assert hasattr(
        QMediaDevices,
        "defaultAudioInput",
    )

    assert hasattr(
        QAudioSource,
        "start",
    )

    assert hasattr(
        QAudioSource,
        "stop",
    )

    assert hasattr(
        QAudioSource,
        "stateChanged",
    )


def test_qaudio_state_symbols_expected_by_adapter_exist():
    for name in (
        "ActiveState",
        "SuspendedState",
        "StoppedState",
        "IdleState",
    ):
        assert hasattr(
            QAudio.State,
            name,
        )


def test_qaudio_error_symbols_expected_by_adapter_exist():
    for name in (
        "NoError",
        "OpenError",
        "IOError",
        "UnderrunError",
        "FatalError",
    ):
        assert hasattr(
            QAudio.Error,
            name,
        )


def test_recovery_after_failure_can_start_new_generation():
    bad = FakeSource(
        start_error=True
    )

    good_io = FakeIODevice()
    good = FakeSource(
        good_io
    )

    factory = Factory(
        [
            bad,
            good,
        ]
    )

    controller = (
        KumaMicrophoneCapture(
            device_provider=lambda:
            FakeDevice(),
            source_factory=factory,
        )
    )

    assert (
        controller.start_capture()
        is False
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.ERROR
    )

    assert (
        controller.start_capture()
        is True
    )

    good_io.push(
        b"ok"
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.CAPTURING
    )


def test_error_signal_does_not_contain_native_exception_details():
    def broken_factory(
        *args,
    ):
        raise RuntimeError(
            "private backend detail"
        )

    controller = (
        KumaMicrophoneCapture(
            device_provider=lambda:
            FakeDevice(),
            source_factory=broken_factory,
        )
    )

    errors = error_events(
        controller
    )

    controller.start_capture()

    assert len(errors) == 1

    assert (
        "private backend detail"
        not in errors[0]
    )


def test_observation_reason_does_not_contain_device_description():
    device = FakeDevice(
        description="Sensitive Device Label"
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        device=device
    )

    controller.probe_availability()

    assert (
        "Sensitive Device Label"
        not in controller.observation.reason
    )


def test_device_description_is_metadata_only_not_capture_truth():
    device = FakeDevice(
        description="Mic"
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        device=device
    )

    controller.probe_availability()

    assert (
        controller.device_description
        == "Mic"
    )

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        controller.observation.microphone_active
        is False
    )


def test_probe_emits_inactive_state_once():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    events = state_events(
        controller
    )

    controller.probe_availability()

    assert (
        len(events)
        == 1
    )

    assert (
        events[0].input_mode
        == VoiceInputMode.INACTIVE
    )


def test_repeated_identical_probe_does_not_duplicate_state_event():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    events = state_events(
        controller
    )

    controller.probe_availability()
    controller.probe_availability()

    assert (
        len(events)
        == 1
    )


def test_start_after_probe_does_not_claim_active_before_bytes():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    controller.probe_availability()
    controller.start_capture()

    assert (
        controller.observation.input_mode
        == VoiceInputMode.INACTIVE
    )

    assert (
        controller.observation.reason
        == "microphone available; capture not yet proven"
    )


def test_stop_terminal_reason_is_bounded_contract_text():
    io_device = FakeIODevice()
    source = FakeSource(
        io_device
    )

    (
        controller,
        _,
        _,
        _,
    ) = make_controller(
        source=source
    )

    controller.start_capture()

    io_device.push(
        b"1"
    )

    controller.stop_capture()

    assert (
        controller.observation.reason
        == "microphone capture stopped"
    )


def test_capture_state_signal_carries_observation_object():
    (
        controller,
        _,
        _,
        _,
    ) = make_controller()

    events = state_events(
        controller
    )

    controller.probe_availability()

    assert isinstance(
        events[0],
        MicrophoneCaptureObservation,
    )


def test_no_audio_signal_surface_exposes_raw_payload():
    text = MODULE.read_text()

    signal_lines = [
        line.strip()
        for line in text.splitlines()
        if "Signal(" in line
    ]

    assert not any(
        "bytes"
        in line.lower()
        or "audio"
        in line.lower()
        for line in signal_lines
    )


def test_capture_controller_public_surface_contains_no_transcribe_method():
    names = {
        name.lower()
        for name in dir(
            KumaMicrophoneCapture
        )
    }

    assert not any(
        "transcrib"
        in name
        or "recogn"
        in name
        for name in names
    )


def test_capture_controller_public_surface_contains_no_execute_method():
    names = {
        name.lower()
        for name in dir(
            KumaMicrophoneCapture
        )
    }

    assert not any(
        name.startswith(
            "execute"
        )
        for name in names
    )


def test_module_compiles_as_plain_python_source():
    compile(
        MODULE.read_text(),
        str(MODULE),
        "exec",
    )
