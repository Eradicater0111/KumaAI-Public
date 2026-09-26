"""Hard-bounded production entry point for one structured UI observation."""

import json
import math
import os
from pathlib import Path
import selectors
import subprocess
import sys
import threading
import time

from app.desktop.contracts import ApplicationIdentity
from app.ui_observation.collector import validate_limits
from app.ui_observation.contracts import StructuredUIObservation, unavailable


MAX_OUTPUT_BYTES = 1024 * 1024
_COLLECTION_LOCK = threading.Lock()
_WORKER = Path(__file__).with_name("_worker.py").resolve()


def _run_worker(command, timeout_seconds):
    deadline = time.monotonic() + timeout_seconds
    process = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=str(_WORKER.parents[2]),
        shell=False,
        close_fds=True,
    )
    output = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                for key, _events in selector.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        break
                    output.extend(chunk)
                    if len(output) > MAX_OUTPUT_BYTES:
                        raise ValueError("Structured UI worker output limit exceeded.")
            process.wait(timeout=max(0, deadline - time.monotonic()))
        if process.returncode != 0:
            raise OSError("Structured UI worker failed.")
        return bytes(output)
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()


def collect_structured_ui(
    expected_application,
    *,
    timeout_seconds=3.0,
    max_nodes=128,
    max_depth=6,
    max_children=32,
):
    """Read one AX tree for an already-trusted frontmost app identity."""

    validate_limits(max_nodes, max_depth, max_children)
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or not 0.05 <= timeout_seconds <= 10
    ):
        raise ValueError("timeout_seconds must be finite and between 0.05 and 10.")

    started = time.monotonic()
    if (
        type(expected_application) is not ApplicationIdentity
        or expected_application.bundle_id is None
        or not expected_application.bundle_id
    ):
        return unavailable("expected_application_incomplete", started)
    if sys.platform != "darwin":
        return unavailable("unsupported_platform", started)
    if not _COLLECTION_LOCK.acquire(blocking=False):
        return unavailable("collection_busy", started)
    try:
        try:
            payload = _run_worker(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(_WORKER),
                    str(expected_application.pid),
                    expected_application.bundle_id,
                    str(max_nodes),
                    str(max_depth),
                    str(max_children),
                ],
                float(timeout_seconds),
            )
        except (TimeoutError, subprocess.TimeoutExpired):
            return unavailable("collection_timeout", started)
        except ValueError:
            return unavailable("worker_output_invalid", started)
        except Exception:
            return unavailable("worker_failed", started)

        finished = time.monotonic()
        if finished - started > timeout_seconds:
            return unavailable("collection_timeout", started)
        try:
            if len(payload) > MAX_OUTPUT_BYTES:
                raise ValueError("Oversized result.")
            result = StructuredUIObservation.from_dict(json.loads(payload))
            if not started <= result.captured_at_monotonic <= finished:
                raise ValueError("Result timestamp is outside this collection.")
            if result.active_application is not None and (
                result.active_application.pid != expected_application.pid
                or result.active_application.bundle_id != expected_application.bundle_id
            ):
                raise ValueError("Worker returned a different application identity.")
            if len(result.elements) > max_nodes:
                raise ValueError("Worker returned too many UI elements.")
            if any(
                len(element.path) > max_depth
                or any(index >= max_children for index in element.path)
                for element in result.elements
            ):
                raise ValueError("Worker returned UI paths outside requested bounds.")
            return result
        except Exception:
            return unavailable("worker_output_invalid", started)
    finally:
        _COLLECTION_LOCK.release()
