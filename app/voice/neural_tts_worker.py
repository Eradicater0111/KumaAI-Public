from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from kokoro_mlx import KokoroTTS


DEFAULT_VOICE = "af_nova"
DEFAULT_SPEED = 0.96


def send(payload):
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
        ),
        flush=True,
    )


def main():
    send({
        "event": "loading",
    })

    tts_context = (
        KokoroTTS.from_pretrained()
    )

    tts = tts_context.__enter__()

    # =====================================================
    # SILENT FIRST-INFERENCE PREWARM
    # =====================================================
    #
    # Loading the model is not enough to warm the complete
    # synthesis path on MLX. The first real utterance otherwise
    # pays the compilation/inference cold-start cost.
    #
    # Generate one tiny hidden WAV now, before announcing READY.
    # It is never played.
    # =====================================================

    warmup_path = Path(
        "/tmp/kuma_nova_prewarm.wav"
    )

    try:
        send({
            "event": "prewarming",
            "voice": DEFAULT_VOICE,
        })

        tts.save(
            "Ready.",
            str(
                warmup_path
            ),
            voice=DEFAULT_VOICE,
            speed=DEFAULT_SPEED,
            sample_rate=48000,
        )

        send({
            "event": "prewarmed",
            "voice": DEFAULT_VOICE,
        })

    finally:
        try:
            warmup_path.unlink(
                missing_ok=True
            )
        except OSError:
            pass

    send({
        "event": "ready",
        "voice": DEFAULT_VOICE,
    })

    try:
        for raw_line in sys.stdin:

            raw_line = (
                raw_line.strip()
            )

            if not raw_line:
                continue

            try:
                request = json.loads(
                    raw_line
                )
            except json.JSONDecodeError as error:
                send({
                    "event": "error",
                    "error": (
                        "Invalid JSON: "
                        f"{error}"
                    ),
                })
                continue

            command = request.get(
                "command"
            )

            if command == "shutdown":
                send({
                    "event": "shutdown",
                })
                return

            if command != "speak":
                send({
                    "event": "error",
                    "error": (
                        f"Unknown command: "
                        f"{command!r}"
                    ),
                })
                continue

            request_id = str(
                request.get(
                    "id",
                    "",
                )
            )

            text = str(
                request.get(
                    "text",
                    "",
                )
            ).strip()

            output = Path(
                str(
                    request.get(
                        "output",
                        "",
                    )
                )
            )

            voice = str(
                request.get(
                    "voice",
                    DEFAULT_VOICE,
                )
            )

            try:
                speed = float(
                    request.get(
                        "speed",
                        DEFAULT_SPEED,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                speed = DEFAULT_SPEED

            if not request_id:
                send({
                    "event": "error",
                    "error": "Missing request id.",
                })
                continue

            if not text:
                send({
                    "event": "error",
                    "id": request_id,
                    "error": "Empty speech text.",
                })
                continue

            if not str(output):
                send({
                    "event": "error",
                    "id": request_id,
                    "error": "Missing output path.",
                })
                continue

            output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            send({
                "event": "generating",
                "id": request_id,
            })

            try:
                generation_started = (
                    time.perf_counter()
                )

                result = tts.save(
                    text,
                    str(output),
                    voice=voice,
                    speed=speed,
                    sample_rate=48000,
                )

                generation_seconds = (
                    time.perf_counter()
                    - generation_started
                )

                if (
                    not output.is_file()
                    or output.stat().st_size <= 0
                ):
                    raise RuntimeError(
                        "No audio was generated."
                    )

                send({
                    "event": "generated",
                    "id": request_id,
                    "output": str(output),
                    "duration": getattr(
                        result,
                        "duration",
                        None,
                    ),
                    "generation_seconds": (
                        generation_seconds
                    ),
                })

            except Exception as error:
                send({
                    "event": "error",
                    "id": request_id,
                    "error": (
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                })

    finally:
        tts_context.__exit__(
            None,
            None,
            None,
        )


if __name__ == "__main__":
    main()
