from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path

import pytest

from app.voice.stt_audio_handoff import (
    STTAudioHandoffObservation,
    STTAudioHandoffStatus,
    STTNativeAudioFormat,
    deliver_ephemeral_native_audio,
)
from app.voice.voice_runtime import (
    VOICE_AUTHORITY_NONE,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[2]
)

MODULE = (
    ROOT
    / "app"
    / "voice"
    / "stt_audio_handoff.py"
)


def _format():
    return STTNativeAudioFormat(
        sample_rate_hz=48000,
        channel_count=2,
        sample_format="Float",
    )


def test_stt_1a_module_compiles():
    ast.parse(
        MODULE.read_text(),
        filename=str(
            MODULE
        ),
    )


def test_stt_1a_authority_markers_are_explicit():
    source = (
        MODULE.read_text()
    )

    for marker in (
        "RAW AUDIO != USER COMMAND",
        "AUDIO HANDOFF != TRANSCRIPT",
        "PARTIAL TRANSCRIPT != USER TURN",
        "FINAL TRANSCRIPT != TOOL PERMISSION",
        "STT != RUNTIME OWNER",
        "CONSUMER FAILURE != MICROPHONE FAILURE",
        "AUTHORITY:NONE",
    ):
        assert marker in source


def test_stt_1a_has_no_runtime_execution_or_persistence_imports():
    tree = ast.parse(
        MODULE.read_text(),
        filename=str(
            MODULE
        ),
    )

    imported_modules = []

    for node in ast.walk(
        tree
    ):
        if isinstance(
            node,
            ast.Import,
        ):
            imported_modules.extend(
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
            imported_modules.append(
                node.module
            )

    forbidden_prefixes = (
        "app.agent",
        "app.memory",
        "app.integration",
        "app.realtime",
        "sqlite3",
        "subprocess",
        "asyncio",
        "threading",
        "pickle",
        "shelve",
    )

    assert all(
        not module.startswith(
            forbidden_prefixes
        )
        for module in imported_modules
    )


def test_stt_1a_does_not_duplicate_voice_transcript_contract():
    source = (
        MODULE.read_text()
    )

    assert (
        "class VoiceTranscript"
        not in source
    )

    assert (
        "from app.voice.voice_runtime import"
        in source
    )


def test_native_audio_format_is_zero_authority_and_normalized():
    audio_format = STTNativeAudioFormat(
        sample_rate_hz=48000,
        channel_count=2,
        sample_format="  Float  ",
    )

    assert (
        audio_format.sample_rate_hz
        == 48000
    )

    assert (
        audio_format.channel_count
        == 2
    )

    assert (
        audio_format.sample_format
        == "Float"
    )

    assert (
        audio_format.authority
        == VOICE_AUTHORITY_NONE
    )


@pytest.mark.parametrize(
    (
        "kwargs",
        "error_type",
    ),
    (
        (
            dict(
                sample_rate_hz=0,
                channel_count=1,
                sample_format="Int16",
            ),
            ValueError,
        ),
        (
            dict(
                sample_rate_hz=16000,
                channel_count=0,
                sample_format="Int16",
            ),
            ValueError,
        ),
        (
            dict(
                sample_rate_hz=16000,
                channel_count=1,
                sample_format=" ",
            ),
            ValueError,
        ),
        (
            dict(
                sample_rate_hz=16000,
                channel_count=1,
                sample_format=123,
            ),
            TypeError,
        ),
    ),
)
def test_native_audio_format_rejects_invalid_metadata(
    kwargs,
    error_type,
):
    with pytest.raises(
        error_type
    ):
        STTNativeAudioFormat(
            **kwargs
        )


def test_empty_payload_is_noop_and_consumer_is_not_called():
    calls = []

    result = (
        deliver_ephemeral_native_audio(
            b"",
            _format(),
            lambda *_args: calls.append(
                "called"
            ),
        )
    )

    assert calls == []

    assert (
        result.status
        is STTAudioHandoffStatus.EMPTY
    )

    assert (
        result.byte_count
        == 0
    )

    assert (
        result.authority
        == VOICE_AUTHORITY_NONE
    )


def test_missing_consumer_preserves_discard_semantics():
    payload = b"\x01\x02\x03"

    result = (
        deliver_ephemeral_native_audio(
            payload,
            _format(),
            None,
        )
    )

    assert (
        result.status
        is STTAudioHandoffStatus.NO_CONSUMER
    )

    assert (
        result.byte_count
        == len(
            payload
        )
    )


def test_configured_consumer_receives_exact_payload_once():
    payload = b"\x10\x11\x12"
    audio_format = _format()
    calls = []

    def consumer(
        observed_payload,
        observed_format,
    ):
        calls.append(
            (
                observed_payload,
                observed_format,
            )
        )

    result = (
        deliver_ephemeral_native_audio(
            payload,
            audio_format,
            consumer,
        )
    )

    assert calls == [
        (
            payload,
            audio_format,
        )
    ]

    assert (
        calls[0][0]
        is payload
    )

    assert (
        result.status
        is STTAudioHandoffStatus.DELIVERED
    )

    assert (
        result.byte_count
        == len(
            payload
        )
    )


def test_consumer_failure_is_fail_soft():
    payload = b"\x01\x02"

    def consumer(
        _payload,
        _format,
    ):
        raise RuntimeError(
            "synthetic STT failure"
        )

    result = (
        deliver_ephemeral_native_audio(
            payload,
            _format(),
            consumer,
        )
    )

    assert (
        result.status
        is STTAudioHandoffStatus.CONSUMER_ERROR
    )

    assert (
        result.byte_count
        == len(
            payload
        )
    )

    assert (
        result.reason
        == "STT audio consumer failed"
    )


def test_handoff_observation_cannot_store_raw_payload_field():
    names = {
        field.name
        for field
        in fields(
            STTAudioHandoffObservation
        )
    }

    assert names == {
        "status",
        "byte_count",
        "audio_format",
        "reason",
        "authority",
    }

    for forbidden in (
        "payload",
        "data",
        "bytes",
        "buffer",
        "audio",
    ):
        assert (
            forbidden
            not in names
        )


def test_dispatcher_has_no_owner_state_or_buffer_surface():
    source = (
        MODULE.read_text()
    )

    # Operational persistence / buffering surfaces are forbidden even
    # as direct source constructs.
    for forbidden in (
        "self._buffer",
        "self._payload",
        "self._audio",
        "open(",
        "write_bytes",
        "write_text",
        "sqlite",
        "VoiceTranscript(",
    ):
        assert (
            forbidden
            not in source
        )

    # Runtime-owner names may legitimately appear in explanatory
    # docstrings stating that STT-1A does NOT call them. Check executable
    # identifier references through the AST instead of raw prose.
    tree = ast.parse(
        source,
        filename=str(
            MODULE
        ),
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

    forbidden_runtime_names = {
        "KumaAgent",
        "KumaGUIRuntime",
        "MissionService",
        "PermissionLevel",
        "QAudioSource",
    }

    assert (
        referenced_names
        .isdisjoint(
            forbidden_runtime_names
        )
    )


def test_non_bytes_payload_is_rejected_before_consumer():
    calls = []

    with pytest.raises(
        TypeError
    ):
        deliver_ephemeral_native_audio(
            bytearray(
                b"\x00"
            ),
            _format(),
            lambda *_args: calls.append(
                "called"
            ),
        )

    assert calls == []


def test_non_callable_consumer_is_rejected():
    with pytest.raises(
        TypeError
    ):
        deliver_ephemeral_native_audio(
            b"\x00",
            _format(),
            object(),
        )
