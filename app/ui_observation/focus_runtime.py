"""Hard-bounded isolated runtime for one native focused UI observation.

The runtime launches a fixed-purpose worker with ``-I -B`` and accepts only the
strict FocusedUIObservation JSON contract.

It performs no AX write, model call, target authorization, permission decision,
keyboard action, or physical execution.
"""

from __future__ import annotations

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
from app.ui_observation.focus_contracts import (
    FOCUS_STATUS_AVAILABLE,
    FocusedUIObservation,
    unavailable_focus,
)


# One focus record contains only bounded application + focused-element metadata.
# Even worst-case escaped Unicode remains far below this boundary.
MAX_FOCUS_OUTPUT_BYTES = (
    64 * 1024
)

_COLLECTION_LOCK = (
    threading.Lock()
)

_WORKER = (
    Path(__file__)
    .with_name(
        "_focus_worker.py"
    )
    .resolve()
)


def _complete_application(
    value: object,
) -> bool:
    return (
        type(value)
        is ApplicationIdentity
        and type(value.pid)
        is int
        and value.pid > 0
        and type(value.bundle_id)
        is str
        and bool(
            value.bundle_id.strip()
        )
    )


def _run_worker(
    command,
    timeout_seconds,
):
    """Drain bounded worker output and always kill/reap before return."""

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
        with (
            selectors.DefaultSelector()
            as selector
        ):
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

                for key, _events in (
                    selector.select(
                        remaining
                    )
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
                        > MAX_FOCUS_OUTPUT_BYTES
                    ):
                        raise ValueError(
                            "Focused UI worker output "
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
                "Focused UI worker failed."
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


def collect_focused_ui(
    expected_application,
    *,
    timeout_seconds=2.0,
) -> FocusedUIObservation:
    """Collect one isolated native focused-element observation.

    ``available`` proves only that the fixed worker established a stable native
    focused element inside the exact expected frontmost application during the
    collection attempt.

    The returned evidence grants no keyboard or execution authority.
    """

    if (
        type(timeout_seconds)
        not in (int, float)
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

    started = time.monotonic()

    if not _complete_application(
        expected_application
    ):
        return unavailable_focus(
            "expected_application_incomplete",
            started,
        )

    if sys.platform != "darwin":
        return unavailable_focus(
            "unsupported_platform",
            started,
        )

    if not _COLLECTION_LOCK.acquire(
        blocking=False
    ):
        return unavailable_focus(
            "collection_busy",
            started,
        )

    try:
        try:
            payload = _run_worker(
                [
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
                ],
                float(
                    timeout_seconds
                ),
            )

        except (
            TimeoutError,
            subprocess.TimeoutExpired,
        ):
            return unavailable_focus(
                "collection_timeout",
                started,
            )

        except ValueError:
            return unavailable_focus(
                "worker_output_invalid",
                started,
            )

        except Exception:
            return unavailable_focus(
                "worker_failed",
                started,
            )

        finished = time.monotonic()

        if (
            finished - started
            > timeout_seconds
        ):
            return unavailable_focus(
                "collection_timeout",
                started,
            )

        try:
            if (
                len(payload)
                > MAX_FOCUS_OUTPUT_BYTES
            ):
                raise ValueError(
                    "Oversized focused UI result."
                )

            decoded = json.loads(
                payload
            )

            result = (
                FocusedUIObservation
                .from_dict(
                    decoded
                )
            )

            if not (
                started
                <= result.captured_at_monotonic
                <= finished
            ):
                raise ValueError(
                    "Focused UI result timestamp "
                    "is outside this collection."
                )

            if (
                result.status
                == FOCUS_STATUS_AVAILABLE
            ):
                application = (
                    result.active_application
                )

                if (
                    application is None
                    or application.pid
                    != expected_application.pid
                    or application.bundle_id
                    != expected_application.bundle_id
                ):
                    raise ValueError(
                        "Focused UI worker returned "
                        "a different application identity."
                    )

            return result

        except Exception:
            return unavailable_focus(
                "worker_output_invalid",
                started,
            )

    finally:
        _COLLECTION_LOCK.release()
