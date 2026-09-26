"""Bounded parent runtime for isolated KUMA 8D2 native correlation."""

from __future__ import annotations

import base64
import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time

from app.desktop.contracts import (
    ApplicationIdentity,
)
from app.ui_observation.focus_target_correlation import (
    MAX_FOCUS_TARGET_CHILDREN,
    MAX_FOCUS_TARGET_DEPTH,
    MAX_FOCUS_TARGET_NODES,
    focus_target_correlation_from_dict,
    focus_target_selector_to_dict,
    unknown_focus_target_correlation,
    validate_focus_target_limits,
)
from app.ui_observation.target_resolution import (
    StructuredUITargetSelector,
)


MAX_FOCUS_TARGET_OUTPUT_BYTES = (
    64 * 1024
)

MAX_SELECTOR_WIRE_BYTES = (
    16 * 1024
)

_COLLECTION_LOCK = (
    threading.Lock()
)

_WORKER = (
    Path(
        __file__
    )
    .with_name(
        "_focus_target_worker.py"
    )
    .resolve()
)


def _encode_selector(
    selector,
):
    payload = json.dumps(
        focus_target_selector_to_dict(
            selector
        ),
        allow_nan=False,
        separators=(
            ",",
            ":",
        ),
    ).encode(
        "utf-8"
    )

    if (
        not payload
        or len(payload)
        > MAX_SELECTOR_WIRE_BYTES
    ):
        raise ValueError(
            "Selector wire payload exceeded bound."
        )

    return base64.b64encode(
        payload
    ).decode(
        "ascii"
    )


def _run_worker(
    command,
    timeout_seconds,
):
    deadline = (
        time.monotonic()
        + timeout_seconds
    )

    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=str(
            _WORKER.parents[2]
        ),
        shell=False,
        close_fds=True,
    )

    output = bytearray()

    try:
        with selectors.DefaultSelector() as selector:
            selector.register(
                process.stdout,
                selectors.EVENT_READ,
            )

            while selector.get_map():
                remaining = (
                    deadline
                    - time.monotonic()
                )

                if remaining <= 0:
                    raise TimeoutError

                for key, _events in selector.select(
                    remaining
                ):
                    chunk = os.read(
                        key.fileobj.fileno(),
                        16384,
                    )

                    if not chunk:
                        selector.unregister(
                            key.fileobj
                        )
                        break

                    output.extend(
                        chunk
                    )

                    if (
                        len(output)
                        > MAX_FOCUS_TARGET_OUTPUT_BYTES
                    ):
                        raise ValueError(
                            "Focus-target worker output "
                            "limit exceeded."
                        )

            process.wait(
                timeout=max(
                    0,
                    deadline
                    - time.monotonic(),
                )
            )

        if process.returncode != 0:
            raise OSError(
                "Focus-target worker failed."
            )

        return bytes(
            output
        )

    finally:
        if process.poll() is None:
            process.kill()

        process.wait()

        if process.stdout is not None:
            process.stdout.close()


def collect_focus_target_correlation_isolated(
    expected_application,
    selector,
    *,
    timeout_seconds=3.0,
    max_nodes=MAX_FOCUS_TARGET_NODES,
    max_depth=MAX_FOCUS_TARGET_DEPTH,
    max_children=MAX_FOCUS_TARGET_CHILDREN,
):
    """Collect one isolated same-process-native focus/target correlation."""

    validate_focus_target_limits(
        max_nodes,
        max_depth,
        max_children,
    )

    if (
        type(timeout_seconds)
        not in (
            int,
            float,
        )
        or type(timeout_seconds)
        is bool
        or not math.isfinite(
            timeout_seconds
        )
        or not (
            0.05
            <= timeout_seconds
            <= 10.0
        )
    ):
        raise ValueError(
            "timeout_seconds must be finite "
            "and between 0.05 and 10."
        )

    if (
        type(expected_application)
        is not ApplicationIdentity
    ):
        raise TypeError(
            "expected_application must be "
            "an exact ApplicationIdentity."
        )

    if (
        type(selector)
        is not StructuredUITargetSelector
    ):
        raise TypeError(
            "selector must be an exact "
            "StructuredUITargetSelector."
        )

    started = (
        time.monotonic()
    )

    def unknown(
        code,
    ):
        return (
            unknown_focus_target_correlation(
                code,
                expected_application=(
                    expected_application
                ),
                selector=selector,
                captured_at_monotonic=(
                    started
                ),
            )
        )

    if (
        type(
            expected_application.pid
        )
        is not int
        or expected_application.pid <= 0
        or type(
            expected_application.bundle_id
        )
        is not str
        or not expected_application.bundle_id
    ):
        return unknown(
            "expected_application_incomplete"
        )

    if sys.platform != "darwin":
        return unknown(
            "unsupported_platform"
        )

    if not _COLLECTION_LOCK.acquire(
        blocking=False
    ):
        return unknown(
            "collection_busy"
        )

    try:
        try:
            selector_token = (
                _encode_selector(
                    selector
                )
            )

            command = [
                sys.executable,
                "-I",
                "-B",
                str(
                    _WORKER
                ),
                str(
                    expected_application.pid
                ),
                expected_application.bundle_id,
                selector_token,
                str(
                    max_nodes
                ),
                str(
                    max_depth
                ),
                str(
                    max_children
                ),
            ]

            payload = (
                _run_worker(
                    command,
                    float(
                        timeout_seconds
                    ),
                )
            )

        except (
            TimeoutError,
            subprocess.TimeoutExpired,
        ):
            return unknown(
                "collection_timeout"
            )

        except ValueError:
            return unknown(
                "worker_output_invalid"
            )

        except Exception:
            return unknown(
                "worker_failed"
            )

        finished = (
            time.monotonic()
        )

        if (
            finished - started
            > timeout_seconds
        ):
            return unknown(
                "collection_timeout"
            )

        try:
            if (
                not payload
                or len(payload)
                > MAX_FOCUS_TARGET_OUTPUT_BYTES
            ):
                raise ValueError(
                    "Invalid worker output size."
                )

            decoded = json.loads(
                payload
            )

            result = (
                focus_target_correlation_from_dict(
                    decoded
                )
            )

            if not (
                started
                <= result.captured_at_monotonic
                <= finished
            ):
                raise ValueError(
                    "Worker timestamp outside "
                    "collection lifetime."
                )

            if (
                result.expected_application.pid
                != expected_application.pid
                or result.expected_application.bundle_id
                != expected_application.bundle_id
            ):
                raise ValueError(
                    "Worker changed expected application."
                )

            if (
                result.selector
                != selector
            ):
                raise ValueError(
                    "Worker changed semantic selector."
                )

            candidate = (
                result.candidate
            )

            if candidate is not None:
                if (
                    candidate.owner_pid
                    != expected_application.pid
                    or len(
                        candidate.path
                    )
                    > max_depth
                    or any(
                        index
                        >= max_children
                        for index
                        in candidate.path
                    )
                ):
                    raise ValueError(
                        "Worker candidate exceeded "
                        "requested source bounds."
                    )

            return result

        except Exception:
            return unknown(
                "worker_output_invalid"
            )

    finally:
        _COLLECTION_LOCK.release()
