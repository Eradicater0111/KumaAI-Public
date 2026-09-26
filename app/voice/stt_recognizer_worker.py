"""
KUMA STT-1D — isolated local MLX Whisper recognizer worker.

This file is intentionally executable as a standalone .voice-venv process.
It does not import KUMA runtime, GUI, permission, memory, or tool modules.

Protocol:
    stdin  -> newline-delimited JSON commands
    stdout -> newline-delimited JSON events

The worker accepts only a verified LOCAL MLX Whisper model directory.
Remote repository identifiers and URLs are rejected. This prevents model
download from becoming an accidental runtime side effect.

Normalized audio arrives as bounded base64 S16LE PCM. It is decoded in memory,
converted to float32 NumPy samples, and passed directly to mlx_whisper.

MODEL LOAD != MICROPHONE CONSENT
MODEL DOWNLOAD != APP STARTUP
RECOGNIZER RESULT != USER TURN
RECOGNIZER PROCESS != RUNTIME OWNER
TRANSCRIPT TEXT != TOOL PERMISSION
AUTHORITY = NONE
"""

from __future__ import annotations

import argparse
import base64
import binascii
from contextlib import redirect_stdout
import json
from pathlib import Path
import re
import sys


TARGET_SAMPLE_RATE_HZ = 16000
TARGET_CHANNEL_COUNT = 1
TARGET_SAMPLE_FORMAT = "Int16LE"

HARD_MAX_SECONDS = 60
MAX_PCM_BYTES = (
    TARGET_SAMPLE_RATE_HZ
    * TARGET_CHANNEL_COUNT
    * 2
    * HARD_MAX_SECONDS
)

MAX_REQUEST_LINE_BYTES = 3_000_000
MAX_TRANSCRIPT_CHARS = 12_000
MAX_REQUEST_ID_CHARS = 128


def send(
    payload,
) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(
                ",",
                ":",
            ),
        ),
        flush=True,
    )


def _bounded_request_id(
    value,
) -> str:
    if not isinstance(
        value,
        str,
    ):
        raise ValueError(
            "invalid request id"
        )

    normalized = (
        value
        .strip()
    )

    if (
        not normalized
        or len(
            normalized
        )
        > MAX_REQUEST_ID_CHARS
    ):
        raise ValueError(
            "invalid request id"
        )

    return normalized


def _local_model_path(
    value,
) -> Path:
    if not isinstance(
        value,
        (
            str,
            Path,
        ),
    ):
        raise ValueError(
            "invalid local model path"
        )

    path = Path(
        value
    ).expanduser()

    if not path.is_absolute():
        raise ValueError(
            "model path must be absolute"
        )

    try:
        resolved = (
            path.resolve(
                strict=True
            )
        )
    except OSError as error:
        raise ValueError(
            "local model path unavailable"
        ) from error

    if not resolved.is_dir():
        raise ValueError(
            "local model path must be a directory"
        )

    if not (
        resolved
        / "config.json"
    ).is_file():
        raise ValueError(
            "local model is incomplete"
        )

    if not any(
        (
            resolved
            / name
        ).is_file()
        for name in (
            "weights.safetensors",
            "weights.npz",
        )
    ):
        raise ValueError(
            "local model is incomplete"
        )

    return resolved


def decode_pcm_request(
    encoded,
):
    if not isinstance(
        encoded,
        str,
    ):
        raise ValueError(
            "audio payload must be base64 text"
        )

    try:
        payload = base64.b64decode(
            encoded,
            validate=True,
        )
    except (
        binascii.Error,
        ValueError,
    ) as error:
        raise ValueError(
            "invalid base64 audio payload"
        ) from error

    if (
        not payload
        or len(
            payload
        )
        > MAX_PCM_BYTES
        or len(
            payload
        )
        % 2
        != 0
    ):
        raise ValueError(
            "invalid bounded S16LE audio payload"
        )

    return payload


def pcm_s16le_to_float32(
    payload: bytes,
):
    if (
        type(
            payload
        )
        is not bytes
        or not payload
        or len(
            payload
        )
        % 2
        != 0
    ):
        raise ValueError(
            "payload must be non-empty complete S16LE samples"
        )

    import numpy as np

    samples = np.frombuffer(
        payload,
        dtype="<i2",
    ).astype(
        np.float32
    )

    samples /= (
        32768.0
    )

    return samples


def _load_provider():
    import mlx_whisper

    return mlx_whisper


def transcribe_pcm(
    payload: bytes,
    model_path: Path,
    *,
    provider=None,
) -> str:
    local_model = (
        _local_model_path(
            model_path
        )
    )

    waveform = (
        pcm_s16le_to_float32(
            payload
        )
    )

    selected_provider = (
        provider
        if provider is not None
        else _load_provider()
    )

    # stdout is the worker's NDJSON protocol channel.
    #
    # Third-party recognizers may print diagnostics even when
    # their own verbose flag is disabled. Quarantine such
    # provider output onto stderr so send() remains the only
    # writer of protocol stdout.
    with redirect_stdout(
        sys.stderr
    ):
        result = (
            selected_provider.transcribe(
                waveform,
                path_or_hf_repo=str(
                    local_model
                ),
                verbose=False,
            )
        )

    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "recognizer result must be a mapping"
        )

    text = result.get(
        "text",
        "",
    )

    if not isinstance(
        text,
        str,
    ):
        raise ValueError(
            "recognizer text must be str"
        )

    normalized = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    if not normalized:
        raise ValueError(
            "recognizer returned empty text"
        )

    if len(
        normalized
    ) > MAX_TRANSCRIPT_CHARS:
        raise ValueError(
            "recognizer text exceeds bound"
        )

    return normalized


def _error_event(
    request_id,
    reason,
):
    payload = {
        "event": "error",
        "reason": str(
            reason
        ),
    }

    if request_id:
        payload[
            "id"
        ] = request_id

    return payload


def serve(
    model_path: Path,
) -> int:
    try:
        local_model = (
            _local_model_path(
                model_path
            )
        )
    except Exception:
        send(
            {
                "event": "unavailable",
                "reason": "local recognizer model unavailable",
            }
        )
        return 2

    try:
        provider = (
            _load_provider()
        )
    except Exception:
        send(
            {
                "event": "unavailable",
                "reason": "recognizer provider unavailable",
            }
        )
        return 3

    send(
        {
            "event": "ready",
            "provider": "mlx-whisper",
            "sample_rate_hz": (
                TARGET_SAMPLE_RATE_HZ
            ),
        }
    )

    for raw_line in sys.stdin.buffer:
        if (
            not raw_line
            or len(
                raw_line
            )
            > MAX_REQUEST_LINE_BYTES
        ):
            send(
                _error_event(
                    None,
                    "invalid recognizer request",
                )
            )
            continue

        try:
            request = json.loads(
                raw_line.decode(
                    "utf-8"
                )
            )
        except Exception:
            send(
                _error_event(
                    None,
                    "invalid recognizer request",
                )
            )
            continue

        if not isinstance(
            request,
            dict,
        ):
            send(
                _error_event(
                    None,
                    "invalid recognizer request",
                )
            )
            continue

        command = request.get(
            "command"
        )

        if command == "shutdown":
            send(
                {
                    "event": "shutdown",
                }
            )
            return 0

        if command != "transcribe":
            send(
                _error_event(
                    None,
                    "unsupported recognizer command",
                )
            )
            continue

        request_id = None

        try:
            request_id = (
                _bounded_request_id(
                    request.get(
                        "id"
                    )
                )
            )

            payload = (
                decode_pcm_request(
                    request.get(
                        "audio_b64"
                    )
                )
            )

            text = (
                transcribe_pcm(
                    payload,
                    local_model,
                    provider=provider,
                )
            )

        except Exception:
            send(
                _error_event(
                    request_id,
                    "recognition failed",
                )
            )
            continue

        send(
            {
                "event": "transcript",
                "id": request_id,
                "text": text,
                "is_final": True,
            }
        )

    return 0


def main(
    argv=None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "KUMA isolated local STT worker"
        )
    )

    parser.add_argument(
        "--model",
        required=True,
        help=(
            "Absolute path to an already-provisioned "
            "local MLX Whisper model."
        ),
    )

    args = parser.parse_args(
        argv
    )

    return serve(
        Path(
            args.model
        )
    )


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
