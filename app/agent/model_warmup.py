from __future__ import annotations

import os
import threading
import time

from ollama import chat


# =========================================================
# KUMA PERF-3D — BACKGROUND DUAL-BRAIN PREWARM
# =========================================================
#
# Performance only:
# - local Ollama models only
# - no user messages
# - no memory
# - no location
# - no internet evidence
# - no tools
# - no action authority
# =========================================================

_STARTED_MODELS: set[str] = set()
_STARTED_LOCK = threading.Lock()


def _prewarm_enabled() -> bool:
    value = str(
        os.environ.get(
            "KUMA_MODEL_PREWARM",
            "1",
        )
        or ""
    ).strip().lower()

    return value not in {
        "0",
        "false",
        "no",
        "off",
        "disabled",
    }


def _resolve_models(
    agent,
) -> list[tuple[str, str]]:
    if agent is None:
        return []

    main_model = str(
        getattr(
            agent,
            "model",
            "",
        )
        or ""
    ).strip()

    synthesis_getter = getattr(
        agent,
        "_perf3c_synthesis_model_name",
        None,
    )

    synthesis_model = ""

    if callable(
        synthesis_getter
    ):
        try:
            synthesis_model = str(
                synthesis_getter()
                or ""
            ).strip()
        except Exception:
            synthesis_model = ""

    ordered = []

    if synthesis_model:
        ordered.append(
            (
                "synthesis",
                synthesis_model,
            )
        )

    if (
        main_model
        and main_model
        != synthesis_model
    ):
        ordered.append(
            (
                "main",
                main_model,
            )
        )

    return ordered


def _ns_to_ms(
    value,
) -> float:
    try:
        return (
            float(
                value
                or 0
            )
            / 1_000_000.0
        )
    except (
        TypeError,
        ValueError,
    ):
        return 0.0


def _warm_one(
    label: str,
    model_name: str,
) -> None:
    start = time.perf_counter()

    try:
        response = chat(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": "Reply OK.",
                },
            ],
            tools=[],
            think=False,
            keep_alive="30m",
            options={
                "num_ctx": 2048,
                "num_predict": 1,
                "temperature": 0.0,
            },
        )

        elapsed = (
            time.perf_counter()
            - start
        )

        load_ms = _ns_to_ms(
            getattr(
                response,
                "load_duration",
                0,
            )
        )

        print(
            "KUMA PREWARM → "
            f"{label} model '{model_name}' ready "
            f"in {elapsed:.3f}s "
            f"(load={load_ms:.1f}ms)."
        )

    except Exception as error:
        # Prewarm is an optimization, never a startup dependency.
        print(
            "KUMA PREWARM → "
            f"{label} model '{model_name}' warm-up failed "
            f"non-fatally: {error}"
        )


def start_model_prewarm(
    agent,
) -> None:
    """
    Start non-blocking local Ollama warm-up threads.

    This function deliberately returns immediately. Model loading may overlap
    with KUMA voice/body startup and normal UI construction.
    """

    if not _prewarm_enabled():
        print(
            "KUMA PREWARM → disabled by KUMA_MODEL_PREWARM."
        )
        return

    # Avoid local-model calls from pytest collection/runtime unless a test
    # explicitly calls the internal helpers with monkeypatching.
    if os.environ.get(
        "PYTEST_CURRENT_TEST"
    ):
        return

    models = _resolve_models(
        agent
    )

    for label, model_name in models:
        with _STARTED_LOCK:
            if model_name in _STARTED_MODELS:
                continue

            _STARTED_MODELS.add(
                model_name
            )

        thread = threading.Thread(
            target=_warm_one,
            args=(
                label,
                model_name,
            ),
            name=(
                "kuma-prewarm-"
                + label
            ),
            daemon=True,
        )

        thread.start()

    if models:
        print(
            "KUMA PREWARM → "
            "background local model warm-up started."
        )
