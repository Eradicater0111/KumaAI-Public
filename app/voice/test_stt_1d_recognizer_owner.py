from __future__ import annotations

import ast
import base64
import json
from pathlib import Path
import struct

import pytest
from PySide6.QtCore import QProcess

from app.voice.stt_recognizer_owner import (
    KumaSTTRecognizerOwner,
)
from app.voice.stt_utterance_normalization import (
    STTNormalizedUtterance,
)
from app.voice.voice_runtime import (
    VOICE_AUTHORITY_NONE,
    VoiceTranscript,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

OWNER_MODULE = (
    ROOT
    / "app"
    / "voice"
    / "stt_recognizer_owner.py"
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


class FakeProcess:
    def __init__(
        self,
        _parent=None,
    ):
        self.readyReadStandardOutput = (
            FakeSignal()
        )

        self.readyReadStandardError = (
            FakeSignal()
        )

        self.finished = (
            FakeSignal()
        )

        self.errorOccurred = (
            FakeSignal()
        )

        self.start_calls = []
        self.writes = []
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.running = False
        self.terminated = 0
        self.killed = 0

    def state(
        self,
    ):
        if self.running:
            return (
                QProcess
                .ProcessState
                .Running
            )

        return (
            QProcess
            .ProcessState
            .NotRunning
        )

    def start(
        self,
        program,
        arguments,
    ):
        self.start_calls.append(
            (
                program,
                list(
                    arguments
                ),
            )
        )
        self.running = True

    def write(
        self,
        payload,
    ):
        self.writes.append(
            bytes(
                payload
            )
        )

        return len(
            payload
        )

    def readAllStandardOutput(
        self,
    ):
        data = bytes(
            self.stdout
        )
        self.stdout.clear()
        return data

    def readAllStandardError(
        self,
    ):
        data = bytes(
            self.stderr
        )
        self.stderr.clear()
        return data

    def push_stdout(
        self,
        payload,
    ):
        self.stdout.extend(
            payload
        )

        self.readyReadStandardOutput.emit()

    def waitForBytesWritten(
        self,
        _timeout,
    ):
        return True

    def waitForFinished(
        self,
        _timeout,
    ):
        return not self.running

    def terminate(
        self,
    ):
        self.terminated += 1
        self.running = False

    def kill(
        self,
    ):
        self.killed += 1
        self.running = False


class ProcessFactory:
    def __init__(
        self,
    ):
        self.instances = []

    def __call__(
        self,
        parent=None,
    ):
        process = FakeProcess(
            parent
        )

        self.instances.append(
            process
        )

        return process


def make_model(
    tmp_path,
):
    model = (
        tmp_path
        / "local-model"
    )

    model.mkdir()

    (
        model
        / "config.json"
    ).write_text(
        "{}"
    )

    (
        model
        / "weights.npz"
    ).write_bytes(
        b"synthetic"
    )

    return model


def make_executable_files(
    tmp_path,
):
    voice_python = (
        tmp_path
        / "python"
    )

    worker = (
        tmp_path
        / "worker.py"
    )

    voice_python.write_text(
        "#!/bin/sh\n"
    )

    worker.write_text(
        "# worker\n"
    )

    return (
        voice_python,
        worker,
    )


def utterance(
    payload=None,
):
    if payload is None:
        payload = struct.pack(
            "<hhh",
            1000,
            0,
            -1000,
        )

    return STTNormalizedUtterance(
        pcm_s16le=payload,
        source_byte_count=len(
            payload
        ),
    )


def build_owner(
    tmp_path,
):
    model = make_model(
        tmp_path
    )

    (
        voice_python,
        worker,
    ) = make_executable_files(
        tmp_path
    )

    factory = (
        ProcessFactory()
    )

    owner = (
        KumaSTTRecognizerOwner(
            model_path=model,
            voice_python=voice_python,
            worker_path=worker,
            process_factory=factory,
        )
    )

    return (
        owner,
        factory,
        model,
        voice_python,
        worker,
    )


def test_owner_constructs_without_starting_process(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    assert (
        factory.instances
        == []
    )

    assert (
        owner.service_ready
        is False
    )


def test_owner_requires_local_complete_model(
    tmp_path,
):
    (
        voice_python,
        worker,
    ) = make_executable_files(
        tmp_path
    )

    factory = (
        ProcessFactory()
    )

    owner = (
        KumaSTTRecognizerOwner(
            model_path=(
                tmp_path
                / "missing"
            ),
            voice_python=voice_python,
            worker_path=worker,
            process_factory=factory,
        )
    )

    assert (
        owner.start()
        is False
    )

    assert (
        factory.instances
        == []
    )


def test_owner_accepts_mlx_whisper_weight_layouts(
    tmp_path,
):
    for index, weight_name in enumerate(
        (
            "weights.safetensors",
            "weights.npz",
        )
    ):
        model = (
            tmp_path
            / f"accepted-model-{index}"
        )

        model.mkdir()

        (
            model
            / "config.json"
        ).write_text(
            "{}"
        )

        (
            model
            / weight_name
        ).write_bytes(
            b"synthetic"
        )

        owner = (
            KumaSTTRecognizerOwner(
                model_path=model
            )
        )

        assert (
            owner._local_model_available()
            is True
        )



def test_owner_rejects_model_safetensors_only(
    tmp_path,
):
    model = (
        tmp_path
        / "wrong-layout"
    )

    model.mkdir()

    (
        model
        / "config.json"
    ).write_text(
        "{}"
    )

    (
        model
        / "model.safetensors"
    ).write_bytes(
        b"synthetic"
    )

    owner = (
        KumaSTTRecognizerOwner(
            model_path=model
        )
    )

    assert (
        owner._local_model_available()
        is False
    )



def test_owner_requires_config_with_valid_weights(
    tmp_path,
):
    model = (
        tmp_path
        / "missing-config"
    )

    model.mkdir()

    (
        model
        / "weights.npz"
    ).write_bytes(
        b"synthetic"
    )

    owner = (
        KumaSTTRecognizerOwner(
            model_path=model
        )
    )

    assert (
        owner._local_model_available()
        is False
    )



def test_explicit_start_uses_voice_python_worker_and_local_model(
    tmp_path,
):
    (
        owner,
        factory,
        model,
        voice_python,
        worker,
    ) = build_owner(
        tmp_path
    )

    assert (
        owner.start()
        is True
    )

    process = (
        factory.instances[0]
    )

    assert process.start_calls == [
        (
            str(
                voice_python
            ),
            [
                str(
                    worker
                ),
                "--model",
                str(
                    model
                ),
            ],
        )
    ]


def test_recognize_refuses_until_worker_ready(
    tmp_path,
):
    (
        owner,
        _,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    owner.start()

    assert (
        owner.recognize(
            utterance()
        )
        is None
    )


def test_ready_event_enables_recognition(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"ready"}\n'
    )

    assert (
        owner.service_ready
        is True
    )


def test_recognize_sends_bounded_audio_only_over_worker_stdin(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"ready"}\n'
    )

    raw = struct.pack(
        "<hhh",
        200,
        0,
        -200,
    )

    request_id = (
        owner.recognize(
            utterance(
                raw
            )
        )
    )

    assert isinstance(
        request_id,
        str,
    )

    request = json.loads(
        process.writes[-1]
        .decode(
            "utf-8"
        )
    )

    assert (
        request[
            "command"
        ]
        == "transcribe"
    )

    assert (
        request[
            "id"
        ]
        == request_id
    )

    assert (
        base64.b64decode(
            request[
                "audio_b64"
            ]
        )
        == raw
    )

    assert (
        "output"
        not in request
    )

    assert (
        "path"
        not in request
    )


def test_owner_does_not_retain_raw_pcm_after_write(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"ready"}\n'
    )

    raw = struct.pack(
        "<hhhh",
        1,
        2,
        3,
        4,
    )

    owner.recognize(
        utterance(
            raw
        )
    )

    assert (
        raw
        not in tuple(
            owner.__dict__.values()
        )
    )


def test_exactly_one_inflight_request_is_allowed(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"ready"}\n'
    )

    first = owner.recognize(
        utterance()
    )

    second = owner.recognize(
        utterance()
    )

    assert isinstance(
        first,
        str,
    )

    assert (
        second
        is None
    )


def test_matching_transcript_event_emits_frozen_voice_transcript(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    transcripts = []

    owner.transcript_ready.connect(
        transcripts.append
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"ready"}\n'
    )

    request_id = (
        owner.recognize(
            utterance()
        )
    )

    event = {
        "event": "transcript",
        "id": request_id,
        "text": "hello KUMA",
        "is_final": True,
    }

    process.push_stdout(
        (
            json.dumps(
                event
            )
            + "\n"
        ).encode(
            "utf-8"
        )
    )

    assert len(
        transcripts
    ) == 1

    transcript = (
        transcripts[0]
    )

    assert isinstance(
        transcript,
        VoiceTranscript,
    )

    assert (
        transcript.text
        == "hello KUMA"
    )

    assert (
        transcript.is_final
        is True
    )

    assert (
        transcript.authority
        == VOICE_AUTHORITY_NONE
    )

    assert (
        owner.request_pending
        is False
    )


def test_stale_transcript_id_is_ignored(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    transcripts = []

    owner.transcript_ready.connect(
        transcripts.append
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"ready"}\n'
    )

    owner.recognize(
        utterance()
    )

    process.push_stdout(
        b'{"event":"transcript","id":"stale","text":"bad","is_final":true}\n'
    )

    assert transcripts == []

    assert (
        owner.request_pending
        is True
    )


def test_error_event_clears_current_request_without_transcript(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    errors = []
    transcripts = []

    owner.recognizer_error.connect(
        errors.append
    )

    owner.transcript_ready.connect(
        transcripts.append
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"ready"}\n'
    )

    request_id = owner.recognize(
        utterance()
    )

    process.push_stdout(
        (
            json.dumps(
                {
                    "event": "error",
                    "id": request_id,
                    "reason": "private backend detail",
                }
            )
            + "\n"
        ).encode(
            "utf-8"
        )
    )

    assert transcripts == []

    assert errors == [
        "KUMA speech recognition failed."
    ]

    assert (
        owner.request_pending
        is False
    )


def test_owner_error_does_not_expose_worker_private_reason(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    errors = []

    owner.recognizer_error.connect(
        errors.append
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"unavailable","reason":"secret provider stack trace"}\n'
    )

    assert errors == [
        "KUMA speech recognition service is unavailable."
    ]

    assert (
        "secret"
        not in errors[0]
    )


def test_shutdown_uses_protocol_and_clears_owner_state(
    tmp_path,
):
    (
        owner,
        factory,
        _,
        _,
        _,
    ) = build_owner(
        tmp_path
    )

    owner.start()

    process = (
        factory.instances[0]
    )

    process.push_stdout(
        b'{"event":"ready"}\n'
    )

    owner.shutdown()

    assert (
        b'{"command":"shutdown"}\n'
        in process.writes
    )

    assert (
        owner.service_ready
        is False
    )

    assert (
        owner.request_pending
        is False
    )


def test_owner_imports_no_provider_or_numpy():
    source = (
        OWNER_MODULE.read_text()
    )

    tree = ast.parse(
        source,
        filename=str(
            OWNER_MODULE
        ),
    )

    modules = []

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            modules.extend(
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
            modules.append(
                node.module
            )

    for forbidden in (
        "mlx",
        "mlx_whisper",
        "numpy",
        "soundfile",
    ):
        assert forbidden not in modules


def test_owner_has_no_gui_runtime_or_tool_submission_surface():
    source = (
        OWNER_MODULE.read_text()
    )

    for forbidden in (
        "KumaGUIRuntime",
        "KumaAgent",
        "MissionService",
        "send_message(",
        "worker.start()",
        "VoiceTranscript(text=",
        "PermissionLevel",
    ):
        assert (
            forbidden
            not in source
        )


def test_owner_explicit_authority_markers():
    source = (
        OWNER_MODULE.read_text()
    )

    for marker in (
        "START RECOGNIZER != MICROPHONE CONSENT",
        "RECOGNIZER READY != USER TURN",
        "VoiceTranscript != TOOL PERMISSION",
        "RECOGNIZER OWNER != RUNTIME OWNER",
        "AUTHORITY = NONE",
    ):
        assert marker in source
