"""
KUMA STT-1C — bounded utterance assembly and deterministic normalization.

Input:
    STT-1A native audio chunks + STTNativeAudioFormat

Output:
    bounded normalized PCM:
    16 kHz / mono / signed 16-bit little-endian

This module does not open a microphone, perform VAD, load a model, create a
VoiceTranscript, submit a user turn, call KUMA runtime owners, or persist audio.

The assembler may retain native audio only in a bounded in-memory bytearray
until explicit finalize(), clear(), overflow, or format mismatch. Clearing drops
retained references; this does not claim cryptographic memory zeroization.

RAW AUDIO BUFFER != USER COMMAND
UTTERANCE FINALIZE != TRANSCRIPT
NORMALIZED AUDIO != PERMISSION
AUDIO PREPARATION != MODEL AUTHORITY
STT-1C AUTHORITY = NONE
"""

from __future__ import annotations

from array import array
from dataclasses import dataclass, field
from enum import Enum
import math
import struct
import sys

from app.voice.stt_audio_handoff import STTNativeAudioFormat
from app.voice.voice_runtime import VOICE_AUTHORITY_NONE


TARGET_RATE_HZ = 16000
TARGET_CHANNELS = 1
TARGET_FORMAT = "Int16LE"

DEFAULT_MAX_SECONDS = 30.0
MIN_MAX_SECONDS = 0.25
HARD_MAX_SECONDS = 60.0

_SAMPLE_WIDTH = {
    "UInt8": 1,
    "Int16": 2,
    "Int32": 4,
    "Float": 4,
}


class STTUtteranceStatus(str, Enum):
    EMPTY = "empty"
    ACCEPTED = "accepted"
    FORMAT_MISMATCH = "format_mismatch"
    OVERFLOW = "overflow"
    FINALIZED = "finalized"
    NO_AUDIO = "no_audio"
    INVALID_AUDIO = "invalid_audio"


@dataclass(frozen=True, slots=True)
class STTUtteranceObservation:
    status: STTUtteranceStatus
    source_byte_count: int
    buffered_byte_count: int
    reason: str
    authority: str = field(default=VOICE_AUTHORITY_NONE, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.status, STTUtteranceStatus):
            raise TypeError("status must be STTUtteranceStatus.")
        if type(self.source_byte_count) is not int or self.source_byte_count < 0:
            raise ValueError("source_byte_count must be a non-negative int.")
        if type(self.buffered_byte_count) is not int or self.buffered_byte_count < 0:
            raise ValueError("buffered_byte_count must be a non-negative int.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be non-empty str.")
        object.__setattr__(self, "reason", self.reason.strip())


@dataclass(frozen=True, slots=True)
class STTNormalizedUtterance:
    pcm_s16le: bytes
    source_byte_count: int
    sample_rate_hz: int = field(default=TARGET_RATE_HZ, init=False)
    channel_count: int = field(default=TARGET_CHANNELS, init=False)
    sample_format: str = field(default=TARGET_FORMAT, init=False)
    authority: str = field(default=VOICE_AUTHORITY_NONE, init=False)

    def __post_init__(self) -> None:
        if type(self.pcm_s16le) is not bytes or not self.pcm_s16le:
            raise ValueError("pcm_s16le must be non-empty bytes.")
        if len(self.pcm_s16le) % 2:
            raise ValueError("pcm_s16le must contain complete Int16 samples.")
        if type(self.source_byte_count) is not int or self.source_byte_count <= 0:
            raise ValueError("source_byte_count must be a positive int.")


@dataclass(frozen=True, slots=True)
class STTUtteranceFinalization:
    status: STTUtteranceStatus
    source_byte_count: int
    normalized: STTNormalizedUtterance | None
    reason: str
    authority: str = field(default=VOICE_AUTHORITY_NONE, init=False)

    def __post_init__(self) -> None:
        allowed = {
            STTUtteranceStatus.FINALIZED,
            STTUtteranceStatus.NO_AUDIO,
            STTUtteranceStatus.INVALID_AUDIO,
        }
        if self.status not in allowed:
            raise ValueError("invalid finalization status.")
        if type(self.source_byte_count) is not int or self.source_byte_count < 0:
            raise ValueError("source_byte_count must be non-negative int.")
        if self.status is STTUtteranceStatus.FINALIZED:
            if not isinstance(self.normalized, STTNormalizedUtterance):
                raise ValueError("FINALIZED requires normalized audio.")
        elif self.normalized is not None:
            raise ValueError("non-finalized result must not contain audio.")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be non-empty str.")
        object.__setattr__(self, "reason", self.reason.strip())


def _sample_format(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("sample format must be str.")
    normalized = value.strip().split(".")[-1]
    if normalized not in _SAMPLE_WIDTH:
        raise ValueError("unsupported native sample format.")
    return normalized


def _decode(payload: bytes, sample_format: str):
    if sample_format == "UInt8":
        return payload

    typecode = {
        "Int16": "h",
        "Int32": "i",
        "Float": "f",
    }[sample_format]

    values = array(typecode)
    values.frombytes(payload)

    expected = {
        "Int16": 2,
        "Int32": 4,
        "Float": 4,
    }[sample_format]

    if values.itemsize != expected:
        raise ValueError("platform scalar width mismatch.")

    if sys.byteorder != "little":
        values.byteswap()

    return values


def _scalar(value, sample_format: str) -> float:
    if sample_format == "UInt8":
        result = (float(value) - 128.0) / 128.0
    elif sample_format == "Int16":
        result = float(value) / 32768.0
    elif sample_format == "Int32":
        result = float(value) / 2147483648.0
    elif sample_format == "Float":
        result = float(value)
    else:
        raise ValueError("unsupported native sample format.")

    if not math.isfinite(result):
        raise ValueError("native audio contains non-finite sample.")

    return max(-1.0, min(1.0, result))


def normalize_native_audio(
    payload: bytes,
    audio_format: STTNativeAudioFormat,
) -> STTNormalizedUtterance:
    if type(payload) is not bytes or not payload:
        raise ValueError("payload must be non-empty bytes.")
    if not isinstance(audio_format, STTNativeAudioFormat):
        raise TypeError("audio_format must be STTNativeAudioFormat.")

    sf = _sample_format(audio_format.sample_format)
    bytes_per_sample = _SAMPLE_WIDTH[sf]
    frame_width = bytes_per_sample * audio_format.channel_count

    if len(payload) % frame_width:
        raise ValueError("native audio ends with incomplete frame.")

    samples = _decode(payload, sf)
    source_frames = len(payload) // frame_width
    if source_frames <= 0:
        raise ValueError("native audio contains no complete frames.")

    channels = audio_format.channel_count

    def mono(frame_index: int) -> float:
        base = frame_index * channels
        total = 0.0
        for offset in range(channels):
            total += _scalar(samples[base + offset], sf)
        return total / channels

    target_frames = max(
        1,
        (
            source_frames * TARGET_RATE_HZ
            + audio_format.sample_rate_hz
            - 1
        )
        // audio_format.sample_rate_hz,
    )

    output = bytearray(target_frames * 2)

    for out_index in range(target_frames):
        numerator = out_index * audio_format.sample_rate_hz
        left_index = numerator // TARGET_RATE_HZ
        fraction_num = numerator % TARGET_RATE_HZ

        if left_index >= source_frames:
            left_index = source_frames - 1

        right_index = min(left_index + 1, source_frames - 1)
        left = mono(left_index)

        if right_index == left_index or fraction_num == 0:
            sample = left
        else:
            right = mono(right_index)
            fraction = fraction_num / TARGET_RATE_HZ
            sample = left + (right - left) * fraction

        sample = max(-1.0, min(1.0, sample))

        if sample <= -1.0:
            pcm = -32768
        elif sample >= 1.0:
            pcm = 32767
        else:
            pcm = int(round(sample * 32767.0))

        struct.pack_into("<h", output, out_index * 2, pcm)

    return STTNormalizedUtterance(
        pcm_s16le=bytes(output),
        source_byte_count=len(payload),
    )


class STTUtteranceAssembler:
    """
    Explicit bounded owner for one in-progress native utterance.
    """

    def __init__(self, *, max_seconds: float = DEFAULT_MAX_SECONDS):
        if type(max_seconds) not in (int, float):
            raise TypeError("max_seconds must be numeric.")

        max_seconds = float(max_seconds)

        if (
            not math.isfinite(max_seconds)
            or max_seconds < MIN_MAX_SECONDS
            or max_seconds > HARD_MAX_SECONDS
        ):
            raise ValueError("max_seconds outside supported bounded range.")

        self._max_seconds = max_seconds
        self._buffer = bytearray()
        self._audio_format = None

    @property
    def max_seconds(self) -> float:
        return self._max_seconds

    @property
    def buffered_byte_count(self) -> int:
        return len(self._buffer)

    @property
    def native_format(self) -> STTNativeAudioFormat | None:
        return self._audio_format

    def _max_bytes(self, audio_format: STTNativeAudioFormat) -> int:
        sf = _sample_format(audio_format.sample_format)
        return int(
            audio_format.sample_rate_hz
            * audio_format.channel_count
            * _SAMPLE_WIDTH[sf]
            * self._max_seconds
        )

    def _wipe_reset(self) -> None:
        if self._buffer:
            self._buffer[:] = b"\x00" * len(self._buffer)
        self._buffer.clear()
        self._audio_format = None

    def clear(self) -> None:
        self._wipe_reset()

    def __call__(
        self,
        payload: bytes,
        audio_format: STTNativeAudioFormat,
    ) -> None:
        self.push(payload, audio_format)

    def push(
        self,
        payload: bytes,
        audio_format: STTNativeAudioFormat,
    ) -> STTUtteranceObservation:
        if type(payload) is not bytes:
            raise TypeError("payload must be bytes.")
        if not isinstance(audio_format, STTNativeAudioFormat):
            raise TypeError("audio_format must be STTNativeAudioFormat.")

        if not payload:
            return STTUtteranceObservation(
                STTUtteranceStatus.EMPTY,
                0,
                len(self._buffer),
                "empty native audio chunk",
            )

        _sample_format(audio_format.sample_format)

        if self._audio_format is None:
            self._audio_format = audio_format
        elif audio_format != self._audio_format:
            source_count = len(payload)
            self._wipe_reset()
            return STTUtteranceObservation(
                STTUtteranceStatus.FORMAT_MISMATCH,
                source_count,
                0,
                "native audio format changed within utterance",
            )

        if len(self._buffer) + len(payload) > self._max_bytes(audio_format):
            source_count = len(payload)
            self._wipe_reset()
            return STTUtteranceObservation(
                STTUtteranceStatus.OVERFLOW,
                source_count,
                0,
                "bounded utterance audio limit exceeded",
            )

        self._buffer.extend(payload)

        return STTUtteranceObservation(
            STTUtteranceStatus.ACCEPTED,
            len(payload),
            len(self._buffer),
            "native audio chunk accepted",
        )

    def finalize(self) -> STTUtteranceFinalization:
        if not self._buffer or self._audio_format is None:
            self._wipe_reset()
            return STTUtteranceFinalization(
                STTUtteranceStatus.NO_AUDIO,
                0,
                None,
                "no buffered utterance audio",
            )

        source_count = len(self._buffer)
        audio_format = self._audio_format
        payload = bytes(self._buffer)

        try:
            normalized = normalize_native_audio(payload, audio_format)
        except Exception:
            return STTUtteranceFinalization(
                STTUtteranceStatus.INVALID_AUDIO,
                source_count,
                None,
                "utterance audio normalization failed",
            )
        finally:
            self._wipe_reset()

        return STTUtteranceFinalization(
            STTUtteranceStatus.FINALIZED,
            source_count,
            normalized,
            "utterance audio normalized",
        )
