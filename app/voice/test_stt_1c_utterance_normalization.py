from __future__ import annotations

import ast
import math
from pathlib import Path
import struct

import pytest

from app.voice.stt_audio_handoff import STTNativeAudioFormat
from app.voice.stt_utterance_normalization import (
    DEFAULT_MAX_SECONDS,
    HARD_MAX_SECONDS,
    TARGET_CHANNELS,
    TARGET_FORMAT,
    TARGET_RATE_HZ,
    STTNormalizedUtterance,
    STTUtteranceAssembler,
    STTUtteranceFinalization,
    STTUtteranceObservation,
    STTUtteranceStatus,
    normalize_native_audio,
)
from app.voice.voice_runtime import VOICE_AUTHORITY_NONE


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "app" / "voice" / "stt_utterance_normalization.py"


def fmt(rate=16000, channels=1, sample_format="Int16"):
    return STTNativeAudioFormat(
        sample_rate_hz=rate,
        channel_count=channels,
        sample_format=sample_format,
    )


def pcm16(*values):
    return struct.pack("<" + "h" * len(values), *values)


def unpack16(payload):
    return struct.unpack("<" + "h" * (len(payload) // 2), payload)


def test_contract_markers():
    source = MODULE.read_text()
    for marker in (
        "RAW AUDIO BUFFER != USER COMMAND",
        "UTTERANCE FINALIZE != TRANSCRIPT",
        "NORMALIZED AUDIO != PERMISSION",
        "AUDIO PREPARATION != MODEL AUTHORITY",
        "STT-1C AUTHORITY = NONE",
    ):
        assert marker in source


def test_default_and_hard_bounds():
    assert DEFAULT_MAX_SECONDS == 30.0
    assert HARD_MAX_SECONDS == 60.0
    assert STTUtteranceAssembler().max_seconds == 30.0


@pytest.mark.parametrize("value", (0.0, 0.1, 60.1, math.inf, math.nan))
def test_invalid_bounds(value):
    with pytest.raises(ValueError):
        STTUtteranceAssembler(max_seconds=value)


def test_empty_chunk_does_not_lock_format():
    assembler = STTUtteranceAssembler()
    result = assembler.push(b"", fmt())
    assert result.status is STTUtteranceStatus.EMPTY
    assert assembler.buffered_byte_count == 0
    assert assembler.native_format is None


def test_chunks_need_not_be_frame_aligned_individually():
    assembler = STTUtteranceAssembler()
    f = fmt()
    assert assembler.push(b"\x01", f).status is STTUtteranceStatus.ACCEPTED
    assert assembler.push(b"\x00", f).status is STTUtteranceStatus.ACCEPTED
    assert assembler.buffered_byte_count == 2


def test_format_change_clears_buffer():
    assembler = STTUtteranceAssembler()
    assembler.push(pcm16(100), fmt())
    result = assembler.push(pcm16(100, 100), fmt(channels=2))
    assert result.status is STTUtteranceStatus.FORMAT_MISMATCH
    assert assembler.buffered_byte_count == 0
    assert assembler.native_format is None


def test_overflow_clears_buffer():
    assembler = STTUtteranceAssembler(max_seconds=0.25)
    f = fmt(rate=4)
    assert assembler.push(pcm16(100), f).status is STTUtteranceStatus.ACCEPTED
    result = assembler.push(pcm16(200), f)
    assert result.status is STTUtteranceStatus.OVERFLOW
    assert assembler.buffered_byte_count == 0


def test_finalize_without_audio():
    result = STTUtteranceAssembler().finalize()
    assert isinstance(result, STTUtteranceFinalization)
    assert result.status is STTUtteranceStatus.NO_AUDIO
    assert result.normalized is None


def test_incomplete_final_frame_is_invalid_and_clears():
    assembler = STTUtteranceAssembler()
    assembler.push(b"\x01", fmt())
    result = assembler.finalize()
    assert result.status is STTUtteranceStatus.INVALID_AUDIO
    assert result.normalized is None
    assert assembler.buffered_byte_count == 0


def test_stereo_downmix_is_deterministic():
    result = normalize_native_audio(
        pcm16(1000, 3000, -1000, 1000),
        fmt(channels=2),
    )
    assert unpack16(result.pcm_s16le) == (2000, 0)


def test_48k_to_16k_constant_resampling():
    result = normalize_native_audio(
        pcm16(*([12000] * 12)),
        fmt(rate=48000),
    )
    assert unpack16(result.pcm_s16le) == (12000, 12000, 12000, 12000)


def test_uint8_center_maps_to_silence():
    result = normalize_native_audio(
        bytes([128, 128]),
        fmt(sample_format="UInt8"),
    )
    assert unpack16(result.pcm_s16le) == (0, 0)


def test_float_clips_to_pcm16():
    result = normalize_native_audio(
        struct.pack("<fff", -2.0, 0.0, 2.0),
        fmt(sample_format="Float"),
    )
    assert unpack16(result.pcm_s16le) == (-32768, 0, 32767)


def test_nonfinite_float_is_rejected():
    with pytest.raises(ValueError):
        normalize_native_audio(
            struct.pack("<f", float("nan")),
            fmt(sample_format="Float"),
        )


def test_unknown_sample_format_is_rejected_before_buffering():
    assembler = STTUtteranceAssembler()
    with pytest.raises(ValueError):
        assembler.push(b"\x00\x00", fmt(sample_format="Unknown"))
    assert assembler.buffered_byte_count == 0


def test_finalize_contract_and_buffer_clear():
    assembler = STTUtteranceAssembler()
    assembler.push(pcm16(1000, -1000), fmt())
    result = assembler.finalize()

    assert result.status is STTUtteranceStatus.FINALIZED
    assert isinstance(result.normalized, STTNormalizedUtterance)
    assert result.normalized.sample_rate_hz == TARGET_RATE_HZ
    assert result.normalized.channel_count == TARGET_CHANNELS
    assert result.normalized.sample_format == TARGET_FORMAT
    assert result.normalized.authority == VOICE_AUTHORITY_NONE
    assert assembler.buffered_byte_count == 0
    assert assembler.native_format is None


def test_assembler_is_stt_1b_callable_consumer():
    assembler = STTUtteranceAssembler()
    assert callable(assembler)
    assembler(pcm16(500), fmt())
    assert assembler.buffered_byte_count == 2


def test_status_objects_are_privacy_minimized():
    assert set(STTUtteranceObservation.__dataclass_fields__) == {
        "status",
        "source_byte_count",
        "buffered_byte_count",
        "reason",
        "authority",
    }
    assert set(STTUtteranceFinalization.__dataclass_fields__) == {
        "status",
        "source_byte_count",
        "normalized",
        "reason",
        "authority",
    }


def test_no_model_runtime_transcript_or_persistence_surface():
    source = MODULE.read_text()
    tree = ast.parse(source, filename=str(MODULE))

    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    forbidden_prefixes = (
        "app.agent",
        "app.memory",
        "app.realtime",
        "app.integration",
        "sqlite3",
        "subprocess",
        "threading",
        "asyncio",
        "pickle",
        "shelve",
    )
    assert all(
        not module.startswith(forbidden_prefixes)
        for module in imported
    )

    for forbidden in (
        "VoiceTranscript(",
        "KumaGUIRuntime",
        "KumaAgent",
        "MissionService",
        "PermissionLevel",
        "QProcess",
        "whisper",
        "mlx_whisper",
        "faster_whisper",
        "speech_recognition",
        "write_bytes",
        "write_text",
    ):
        assert forbidden not in source
